# 04｜媒体 Desired State 对账

> 前置：[Foundation](../01-foundation/README.md)、[Stream Gateway Adapter](../03-stream-gateway-adapter/README.md)
>
> 交付：可复用的媒体 Desired State 构造、启动/周期对账和 MediaMTX 重启恢复；无新公共路由

PostgreSQL 保存全部 CameraSource Desired State；MediaMTX Path 是可重建的 Runtime State。本切片
负责后台恢复路径，不实现 Camera CRUD、Playback 或新的 HTTP handler。

## 本切片负责什么

- 在 Cameras Application 中提供从最新 `Camera` 聚合构造 `DesiredSource` 的纯函数。04 的后台
  对账使用它，05 创建、07 Playback 和 09 更新也必须复用它，避免各自拼接上游 RTSP URL。
- 实现一次完整对账：读取双方快照，计算缺失、漂移和孤儿 Path，再调用现有
  `ensure_path` / `release_path`。
- 用 FastAPI lifespan 管理立即执行一次、之后周期执行的后台任务。
- 用 PostgreSQL session advisory lock 保证同一时刻只有一个 Backend 进程执行一轮对账。
- 记录不含凭据、完整 RTSP URL 或远端配置的轮次汇总日志。

以下内容不在 04 实现：

- Camera 创建、更新和删除后的即时调用。05、09、10 在各自数据库提交后调用媒体端口。
- Playback 的 Source 存在性检查、`3s` 预算、single-flight 和 HTTP 错误转换，这些属于 07。
- Camera/Source 运行状态聚合、WHEP 播放器、媒体健康路由、指标框架、Outbox/Saga 或通用任务
  调度框架。

## 与即时同步的边界

提交后才能访问媒体端口的公共事务规则见
[Foundation](../01-foundation/README.md#持久化与事务)。具体调用分别由
[05 创建](../05-camera-create/README.md#后端顺序)、
[09 更新](../09-camera-update-default-source/README.md#完整更新-camera)和
[10 删除](../10-camera-delete/README.md#删除语义)实现。04 只提供共享 Desired State 构造和后台恢复，
不安装 ORM 事件、Repository hook 或隐式提交回调。

## 代码位置与接口

- `app/modules/cameras/application/media.py`：提供单 Source 和整 Camera 的 `DesiredSource` 构造
  函数，内部调用 `build_mediamtx_source_url()`；返回对象的默认表示不得包含上游 URL。
- `app/modules/cameras/application/reconciliation.py`：保存差异计算、单轮执行结果、
  `reconcile_once()` 和周期 Runner；只依赖 Application Port 与 `StreamGatewayPort`。
- `app/modules/cameras/application/ports.py`：增加只读 `CameraMediaStateReader` 和跨实例
  `MediaReconciliationLease`。成功取得 Lease 时，上下文返回绑定同一数据库连接的 Reader；未取得
  时返回 `None`。Application 不接触 SQLAlchemy Connection、Session 或 ORM Row。
- `app/modules/cameras/persistence/reconciliation.py`：实现 PostgreSQL 全量读取和 advisory lock。
- `app/modules/stream_gateway/ports.py`：公开标准 UUID v4 Path 名称到 Source ID 的纯解析函数；
  Adapter 和 Reconciler 复用同一个所有权判断，不在两个模块复制规则。
- `app/factory.py`：组装 Reader、Lease、Reconciler 和后台任务，并保证任务先于 HTTP Client 与
  数据库连接池关闭；应用工厂增加窄范围 Runner factory 测试注入点，不引入通用调度框架。

全量 Reader 使用一条按 Camera、Source 顺序排列的 `LEFT JOIN` 查询读取全部 Camera 与 Source，
在 Session 关闭前通过现有 Mapper 重建不可变聚合。单条 SQL 保证本次数据库结果来自同一个语句
快照，也能让“Camera 没有 Source”等损坏数据进入聚合检查。ORM Row 不离开持久化模块。

读取数据库失败或任一聚合损坏时，本轮不执行任何 MediaMTX 写操作。数据库中的孤儿 Source 不会
生成 Desired State；其同名远端 UUID Path 如果存在，会按远端孤儿处理。

## 单轮执行顺序

每轮严格执行以下步骤：

1. 尝试取得 advisory lock；未取得时记录 `skipped_lock`，不读取双方快照，也不调用媒体写接口。
   取得时同时得到只读 Reader，后续数据库快照复用持锁 Connection。
2. 获取一份完整 MediaMTX 配置快照。快照不可用或不完整时立即放弃本轮，不基于部分结果修改
   Path。
3. 读取一份完整 PostgreSQL Camera/Source 快照，并使用共享纯函数构造 Desired State。读取失败
   或聚合损坏时放弃本轮。
4. 按 Source ID 计算三个互斥集合：
   - 数据库有、远端没有：缺失；
   - 双方都有，但 `source` 不完全相等、`sourceOnDemand is not False`，或 Adapter 标记字段未知：
     漂移；
   - 远端属于[受管 Path](../README.md#冻结决策)、数据库没有：孤儿。
5. 先按 Source ID 顺序逐项 `ensure_path` 缺失和漂移 Path，再按 Source ID 顺序逐项
   `release_path` 孤儿 Path。非受管 Path 完全忽略。
6. 单项失败继续处理其余项，并把轮次记为 `partial_failure`；同一调用不自动重试，也不在本轮
   重新获取快照。下一轮必须重新读取双方完整快照。
7. 在成功、失败或取消路径释放 advisory lock，再结束本轮。

MVP 使用顺序写入，不提前加入批处理队列、并发 worker 或按 Camera 分片。一次对账结束后才安排
下一次，因此同一进程不会出现重叠轮次。

## 锁与并发

- 使用固定、代码内记录的有符号 64 位 lock key 调用 `pg_try_advisory_lock`；禁止使用进程随机化
  的 Python `hash()`。本阶段不增加数据库表或迁移。
- 锁使用专用 PostgreSQL Connection 的 session lock。取得锁后先结束获取锁产生的短事务，远端
  HTTP 调用期间只持有 Connection 和 session lock，不持有数据库事务。
- Lease 返回的 Reader 复用这条 Connection，并只在执行全量 `LEFT JOIN` 时开启短只读事务；读取
  结束后先结束事务，再执行媒体写入。这样即使 `database_pool_size=1` 且 `max_overflow=0` 也不会
  因为等待第二条连接而卡住。
- Connection 在整轮内不能归还连接池。`finally` 中执行 `pg_advisory_unlock`；连接中断或关闭是
  最后的自动释放保障，避免带锁连接回到池中。
- 锁只排除其他 Reconciler，不阻塞 CRUD 或 Playback。快照完成后的并发提交可能让本轮短暂使用
  旧数据；系统空闲后，后续成功轮次必须以当时数据库数据为准恢复一致。
- 删除与 Playback、更新与即时同步的交错行为分别在 07、09、10 实现，并在 11 做组合验收；04
  只证明晚到的受管孤儿最终会被删除，数据库存在的 Source 最终会被恢复。

## 周期、退避和 lifespan

新增并同步到 `.env.example`、`backend/.env.local.example` 与 `compose.yaml` 的配置：

| Settings 字段                              | 环境变量                                   | 默认值 | 规则             |
| ------------------------------------------ | ------------------------------------------ | ------ | ---------------- |
| `media_reconciliation_interval_seconds`    | `MEDIA_RECONCILIATION_INTERVAL_SECONDS`    | `30`   | 大于 `0`         |
| `media_reconciliation_max_backoff_seconds` | `MEDIA_RECONCILIATION_MAX_BACKOFF_SECONDS` | `300`  | 大于等于正常间隔 |

- lifespan 创建 Database Runtime 和 `MediaMTXAdapter` 后启动后台任务，不等待首次对账完成再开放 API；
  MediaMTX 或对账失败不能阻止 Backend 启动，也不改变现有 readiness。
- Runner 启动后立即执行第一轮。完整成功后，从该轮结束时起等待正常间隔。
- 数据库读取失败、配置快照失败、部分写失败或未预期异常都算失败轮次。连续失败使用
  `min(interval × 2^n, max_backoff)`，并在该值的 `50%–100%` 范围取可测试的随机抖动；完整成功
  后清零。未取得锁不增加失败次数，按正常间隔再次尝试。
- 应用关闭时先取消 Runner，并最多等待 `5s`。取消必须传播，不能被普通错误处理吞掉；任务退出
  后才关闭共享 MediaMTX HTTP Client 和 Database Runtime。
- 生产应用始终启动 Runner。无关的单元/API 测试通过应用工厂的专用注入点使用可控 Runner，不能
  依赖真实 PostgreSQL 或 MediaMTX 后台连接。

## 日志与安全

每轮只记录一条 Reconciler 汇总，稳定字段包括：

```text
operation=media_reconciliation
outcome=success|partial_failure|skipped_lock|database_error|gateway_unavailable|
        gateway_invalid_response|unexpected_error
duration_ms desired_count managed_path_count ensured_count released_count failed_count
next_delay_seconds
```

Adapter 继续负责单次 I/O 的脱敏日志。Reconciler 不记录用户名、密码、后缀、期望 `source`、远端
`source`、完整配置快照、异常链文本或持久化缓存。后台任务没有请求 Trace ID 时使用 `-`。

## 实施步骤

1. 增加共享 Desired State 构造函数和 Path 所有权解析函数，并补纯函数测试。
2. 增加 Reader/Lease Port 及 PostgreSQL 实现，验证全量聚合读取和 session lock 释放。
3. 实现纯差异计算、单轮协调与稳定结果分类，再实现周期、退避和取消。
4. 在 Settings、环境示例、Compose 和 lifespan 中完成装配；保持公共路由和 OpenAPI 不变。
5. 补齐单元、PostgreSQL 集成、lifespan、敏感数据和恢复测试，再运行 Backend 全量门禁。

## 验收

- 纯差异测试覆盖无变化、缺失、已知/未知字段漂移、孤儿、非受管 Path 和确定性处理顺序。
- 清空 Fake MediaMTX 配置后，一轮能恢复全部数据库 Source；下一轮无重复变更。
- 配置快照失败、数据库读取失败或聚合损坏时零写入；单项失败不阻断其他项，下一轮重新获取双方
  快照后能成功。
- 两个 Reconciler 竞争时只有一个读取并写入；正常完成、异常和任务取消后 lock 都能再次取得，
  连接池中不遗留 session lock；最小连接池配置也能完成一轮对账。
- Backend 启动不等待 MediaMTX；关闭顺序为 Runner、MediaMTX Client、Database Runtime，且在
  限时内完成。
- 直接向测试数据库提交合法 Camera、完全不执行即时媒体调用，后续对账仍能恢复 Path，证明提交
  后崩溃窗口不依赖 CRUD hook。
- 并发提交造成的暂时旧写入，在停止并发后的下一轮恢复为数据库最新配置；对账不会修改数据库
  Camera，也不会删除非受管 Path。
- 日志、异常、默认对象表示和测试失败输出不包含测试凭据、完整 RTSP URL 或远端配置。

实现后至少执行：

```bash
cd backend
uv run pytest tests/modules/cameras/test_media.py \
  tests/modules/cameras/test_media_reconciliation.py \
  tests/modules/cameras/test_reconciliation_persistence.py \
  tests/test_config.py tests/test_main.py
uv run pytest
uv run ruff check .
uv run ruff format --check .

cd ..
bash scripts/check-cameras-contracts.sh
bash scripts/check-cameras-sensitive-data.sh
docker compose config
```

需要 PostgreSQL 的测试必须使用独立 `TEST_DATABASE_URL`；未配置导致的跳过不能算作本切片验收
通过。真实 MediaMTX 重启、CRUD/Playback 交错和部署容量由 11 使用完整系统再次验证。
