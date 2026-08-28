# 媒体 Desired State 对账

> 相关文档：[Cameras 基础能力](foundation.md)、[Stream Gateway](stream-gateway.md)

PostgreSQL 保存全部 CameraSource Desired State；MediaMTX Path 是可丢失、可重建的运行时配置。
Backend 启动后立即在后台执行首轮对账，之后周期执行，用数据库恢复缺失或漂移的 Path，并清理
数据库中已不存在的受管孤儿 Path。

## 职责与边界

- `cameras/application/media.py` 从最新 `Camera` 聚合构造 `DesiredSource`。创建、更新、Playback 和
  后台对账必须复用这里的安全 RTSP URL 构造，不能各自拼接凭据或上游地址。
- `cameras/application/reconciliation.py` 负责纯差异计算、单轮执行、结果分类、周期和退避。
- `cameras/persistence/reconciliation.py` 用 PostgreSQL 完成全量聚合读取和跨实例互斥。
- `stream_gateway` 仍只负责 MediaMTX 协议适配、受管 Path 判断和实际 I/O，不读取 Camera 数据库。
- `app/factory.py` 只组装并管理这个窄用途后台任务，不提供通用任务调度框架。

Camera 创建、更新和删除提交后的即时媒体调用属于各自业务用例；Playback 的存在性检查、预算、
single-flight 和 HTTP 错误转换属于播放用例。对账不实现 Camera CRUD、运行状态聚合、播放器、
媒体健康路由、指标框架或事务级 Outbox/Saga。

## Desired State 与所有权

每个数据库 Source 生成一项不可变 `DesiredSource`：

- Path 名称是 Source ID 的小写标准 UUID v4 文本。
- `source` 使用 Camera 当前主机、端口、凭据和 Source 后缀生成，并按 RTSP URI 组件安全编码。
- `sourceOnDemand` 固定为 `false`。
- Source 必须属于传入 Camera；跨 Camera 拼接会在写入 MediaMTX 前被拒绝。
- 包含凭据的上游 URL 不进入对象默认表示、日志、异常或持久化缓存。

只有能严格解析为小写标准 UUID v4 的远端 Path 属于 Cameras。其他名称即使使用 RTSP Source，
也不比较、不覆盖、不删除。受管 Path 的 `source` 或 `sourceOnDemand` 缺失、类型错误或与数据库
不同，都视为漂移并由完整 Desired State 覆盖。

## 单轮行为

每轮按以下固定顺序执行：

1. 非阻塞尝试取得 PostgreSQL session advisory lock。竞争失败返回 `skipped_lock`，不读取数据库、
   MediaMTX 快照，也不执行写入。
2. 获取一份完整 MediaMTX 配置快照。远端不可用或无法证明分页完整时立即结束，禁止依据部分数据
   覆盖或删除 Path。
3. 使用持锁 Connection 读取一份完整 PostgreSQL Camera/Source 快照，并构造全部 Desired State。
   读取、Mapper、聚合不变量或 Desired State 构造失败时整轮零写入。
4. 按 Source ID 计算缺失/漂移 Path 和受管孤儿 Path。重复 Source ID 会让差异计算失败，不能被
   `dict` 静默覆盖。
5. 按 Source ID 顺序先 `ensure_path` 所有缺失/漂移项，再 `release_path` 所有孤儿项。先恢复后删除
   可降低取消或进程退出时只完成破坏性操作的风险。
6. 单项写失败只增加 `failed_count`，继续处理其余项；本轮不重试、不重新取快照，下一轮从双方完整
   快照重新计算。

单轮结果只使用 `success`、`partial_failure`、`skipped_lock`、`database_error`、
`gateway_unavailable`、`gateway_invalid_response` 和 `unexpected_error`。除 `success` 与正常锁竞争外，
其余结果都会增加 Runner 的连续失败次数。

## 数据库锁与并发

- 锁使用代码中固定的有符号 64 位 key，不能改用受进程随机种子影响的 `hash()`。
- Lease 在专用 PostgreSQL Connection 上持有 session advisory lock，并把同一 Connection 交给只读
  Reader；`pool_size=1, max_overflow=0` 时也不能再申请第二条连接。
- Reader 用一条有固定排序的 `LEFT JOIN` 重建全部 Camera 聚合。没有 Source 的 Camera 也必须进入
  Mapper 并报告损坏，不能被内连接静默漏掉。
- 数据查询只在短只读事务中执行；MediaMTX HTTP 调用期间保留 session lock，但不持有数据库事务。
- 正常、异常和取消路径都必须释放锁。无法证明解锁成功时丢弃底层连接，禁止带锁连接返回连接池。
- 锁只排除其他 Reconciler，不阻塞 CRUD 或 Playback。快照后的并发提交允许造成短暂旧写，系统
  空闲后的下一轮必须以最新数据库状态恢复一致。

## 周期与资源生命周期

| 环境变量                                   | 默认值 | 约束               |
| ------------------------------------------ | ------ | ------------------ |
| `MEDIA_RECONCILIATION_INTERVAL_SECONDS`    | `30`   | 大于 `0`           |
| `MEDIA_RECONCILIATION_MAX_BACKOFF_SECONDS` | `300`  | 不小于正常轮询间隔 |

Runner 启动后立即执行首轮；完整成功和锁竞争后，从本轮结束时起等待正常间隔。失败轮次按
`interval × 2^n` 增长到最大值，再在计算结果的 `50%–100%` 范围加入随机抖动；成功后清零。
轮次串行执行，同一进程不会重叠。

FastAPI lifespan 在 Database Runtime 和共享 MediaMTX Client 创建后启动 Runner，不等待首轮完成，
因此对账或 MediaMTX 故障不会阻止 Backend 开放 API，也不会改变只检查 PostgreSQL 的 readiness。
关闭时先取消 Runner 并最多等待 5 秒，再关闭 MediaMTX Client 和数据库连接池。取消必须传播，
后台任务的非取消退出必须留下错误日志。

## 日志与安全

Runner 使用稳定事件记录脱敏汇总：成功无变更和锁竞争为 DEBUG，有 ensure/release 为 INFO；失败
首次出现、类型变化或距离上次 WARNING 达到 30 分钟时为 WARNING，其余同类持续故障为 DEBUG。
真正 `success` 后只输出一条恢复 INFO，`skipped_lock` 不清除日志故障状态，也不计入恢复事件的失败
轮数。日志提醒状态与现有退避计数分开，因此锁竞争仍按原行为清零退避，但不会伪装成依赖恢复。

整轮依赖故障省略五个无意义零计数，只有 `partial_failure` 记录处理计数；恢复事件保留有意义的
ensure/release 0。Adapter 单次 I/O 使用 `stream_gateway.io` DEBUG，默认级别只保留 Runner 业务影响。
停止超时和异常退出使用 `media_reconciliation.runner_exit` ERROR，并通过统一 helper 仅记录异常类型
和代码位置。

对账日志不得记录用户名、密码、Source 后缀、期望或远端 `source`、完整 RTSP URL、完整配置快照、
原始异常文本或响应正文。trace 由统一 Handler 自动补充；后台任务没有 HTTP 上下文时直接省略，
不使用 `-` 占位。

日志采集器应启用 `BACKEND_LOG_FORMAT=json`，按 `media_reconciliation.round_completed`、
`round_failed`、`recovered` 和 `runner_exit` 事件及稳定字段处理；默认 console 面向人工查看，不保证
完整文本可供正则长期解析。SQL 调试由独立的 `DATABASE_ECHO` 控制，不会因 Backend DEBUG 或对账
故障自动开启。

## 长期验证

相关测试覆盖纯差异、完整快照失败零写入、单项失败继续、下一轮恢复、失败退避、任务取消、最小
连接池、跨实例锁竞争、损坏聚合和敏感数据过滤：

```bash
cd backend
uv run pytest tests/modules/cameras/test_media.py \
  tests/modules/cameras/test_media_reconciliation.py \
  tests/modules/cameras/test_reconciliation_persistence.py \
  tests/test_config.py tests/test_main.py
```

PostgreSQL 集成测试要求独立的 `TEST_DATABASE_URL`；跳过这些测试不等于锁和 Reader 已通过验证。
真实 MediaMTX 重启，以及 CRUD/Playback 与对账交错，仍由
[发布门禁](../../plans/cameras-mvp/11-release-gates/README.md)在完整系统中验证。
