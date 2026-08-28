# 02｜业务日志事件改造与持续故障降噪

## 任务目标

把 MediaMTX、媒体对账、Runner 生命周期和 Camera 完整性日志改成“简短中文消息 + 稳定字段”，
删除 message/extra 重复和 `-` 占位。持续故障只在首次、类型变化、定时提醒和恢复时进入默认日志。

## 当前上下文 / 前置条件

- 必须先完成 `01-logging-foundation.md`，并阅读同目录 `README.md` 的全局字段和安全规则。
- Adapter 当前每次 I/O 都调用 `_log_io()`。
- Runner 当前每轮都调用 `_log_round()`，并已有可注入 monotonic clock。
- `reconcile_once()` 的结果、退避公式、sleep 时间和取消传播属于既有行为，不得因日志改造变化。
- Adapter/Runner 不得保存异常文本、远端响应、DesiredSource 或 RTSP URL。
- trace 已由任务 1 的 Handler Filter 自动补充，业务调用不再手工写 `trace_id`。

## 实施范围

修改：

- `backend/src/app/modules/stream_gateway/services/mediamtx.py`
- `backend/src/app/modules/cameras/application/reconciliation.py`
- `backend/src/app/modules/cameras/application/create.py`
- `backend/src/app/factory.py`
- `backend/src/app/modules/cameras/persistence/integrity.py`
- `backend/tests/modules/stream_gateway/test_mediamtx_adapter.py`
- `backend/tests/modules/cameras/test_media_reconciliation.py`
- `backend/tests/modules/cameras/test_camera_create.py`
- `backend/tests/modules/cameras/test_camera_create_api.py`
- `backend/tests/modules/cameras/test_models.py`
- `backend/tests/test_main.py`
- `docs/modules/cameras/stream-gateway.md`
- `docs/modules/cameras/media-reconciliation.md`
- `docs/modules/cameras/camera-create.md`

稳定事件名：

- `stream_gateway.io`
- `media_reconciliation.round_completed`
- `media_reconciliation.round_failed`
- `media_reconciliation.recovered`
- `media_reconciliation.runner_exit`
- `camera.media_sync_degraded`
- `camera.reference_integrity_failed`

## 明确不做

- 不改变 MediaMTX HTTP、分页预算、错误转换或返回类型。
- 不改变对账计划、写入顺序、锁、退避和取消行为。
- 不增加指标、告警平台或持久化故障状态。
- 不修改 HTTP access log。
- 不通过记录异常文本、请求或响应换取诊断信息。

## 实施步骤

1. 重写 Adapter `_log_io()`：
   - message 只使用总览事件表固定的成功/失败中文文本。
   - `operation/outcome/duration_ms/error_type/source_id/path_count` 按事件表条件放入 `extra`：失败
     快照不写无意义的 `path_count=0`，ensure/release 不写固定为 `1` 的 Path 数。
   - 不再传 trace，不构造 `-` 占位。
   - 单次 I/O 成功和失败都使用 `DEBUG`，业务影响由 Application/Runner 表达。
2. 为 `create_camera()` 增加请求级业务告警：
   - 保持数据库提交、逐 Source 尽力同步、Runtime 快照和响应行为不变。
   - 继续捕获 Port 已声明的两类脱敏错误，只额外累计失败次数；一次请求无论发生几次 Adapter
     失败，最多记录一条 `camera.media_sync_degraded` WARNING。
   - `failed_count` 精确表示本次请求捕获的失败 Port 调用数：每个失败的 `ensure_path` 计一次，最后
     的 Runtime 快照失败再计一次；未调用和正常离线投影不计入。
   - 事件只记录 `operation/outcome/camera_id/failed_count`，不记录 Camera、Source 列表、异常文本或
     RTSP URL；Adapter DEBUG 保留单次诊断信息。
3. 重写 Runner 日志：
   - 成功无变更和锁竞争为 `DEBUG`。
   - 成功且 `ensured_count + released_count > 0` 为 `INFO`。
   - 首次失败或失败 outcome 变化为 `WARNING`。
   - 相同 outcome 持续时为 `DEBUG`；距离上次 WARNING 达到 30 分钟时提醒。
   - 只有 `success` 能证明依赖恢复并输出一条恢复 `INFO`；`skipped_lock` 只记 DEBUG，不清除日志
     故障状态、不触发恢复，也不增加故障次数。
4. 退避计数继续完全沿用现有 `consecutive_failures` 行为，包括锁竞争后清零。日志降级状态单独保存：
   首次失败时间、累计实际失败轮数、上一次 outcome、上一次 WARNING 时间。这样锁竞争不会伪装成
   恢复，也不会改变退避公式、sleep 时间或取消传播。所有时间使用现有注入的 monotonic clock，
   测试不得依赖真实时间。
   - 每轮只读取一次结束时刻，同时用于 `duration_ms` 和日志状态计算。
   - 首次失败、WARNING 提醒和恢复持续时间都以轮次结束时刻为基准；恢复时长包含中间的锁竞争
     等待，但锁竞争不增加失败轮数。
   - outcome 变化时立即 WARNING，并把该时刻作为新的 30 分钟提醒起点；首次失败时刻不重置。
5. Runner 按总览事件表附加字段：网关/数据库等整轮失败不写五个零计数；只有
   `partial_failure` 写入计数；恢复事件保留 ensure/release 的有效 `0`。
6. `factory.py` 的停止和退出日志改成固定中文 message 与
   `media_reconciliation.runner_exit`/稳定 outcome。`except` 分支和 done callback 都调用任务 1 的
   安全异常 helper，只把纯字符串 `error_type/error_frames` 放入 `extra`；不得向 LogRecord 传入异常
   对象、异常文本或原始 `exc_info`。正常但意外退出不附加空异常字段。
7. Camera 完整性报告改用模块 Logger，确保组件固定为 `camera.integrity`；仍然每项一条 `ERROR`，
   只附加 kind、Camera ID 和可选 Source ID。
8. 业务测试主要断言 `LogRecord` 的 event、字段是否存在及级别；最终文本、字段短键和转义只由
   任务 1 的 Formatter 测试固定。
9. 更新 Stream Gateway、媒体对账和 Camera Create 文档中的日志级别、业务告警、降噪与恢复规则。

## 验证方式

```bash
cd backend
uv run pytest \
  tests/modules/stream_gateway/test_mediamtx_adapter.py \
  tests/modules/cameras/test_media_reconciliation.py \
  tests/modules/cameras/test_camera_create.py \
  tests/modules/cameras/test_camera_create_api.py \
  tests/modules/cameras/test_models.py \
  tests/test_main.py
uv run ruff check .
uv run ruff format --check .
```

必须覆盖：

1. 连续七次 `gateway_unavailable`：默认级别只出现首次 WARNING，其余为 DEBUG。
2. 失败类型变为 `database_error`：立即出现新的 WARNING。
3. 相同故障超过 30 分钟：出现一条提醒 WARNING。
4. 下一轮成功：出现且仅出现一条恢复 INFO。
5. 故障后先出现 `skipped_lock`：只增加一条 DEBUG，不输出恢复；再 success 时才输出一次恢复 INFO，
   恢复事件的失败次数不包含锁竞争轮次。
6. 成功且无变更：只有 DEBUG；发生 ensure/release：出现 INFO。
7. Camera 创建提交后发生多个 Adapter 错误：Adapter 有多条 DEBUG，但默认级别只有一条带请求 trace
   的 `camera.media_sync_degraded` WARNING，HTTP 仍返回既有 `201`。
8. 所有日志均不包含 `trace=-`、`source=-`、无意义零计数、密码、完整 URL 或远端响应正文。
9. 原有退避延迟序列、Camera 创建事务/响应和取消测试保持不变。

## 完成标准

- 同一轮配置快照不可用在默认级别只出现一条业务告警。
- 七轮相同故障不再产生十四条 WARNING。
- 恢复事件明确可见，并带失败次数和持续时间。
- DEBUG 开启后仍能查看 Adapter 单次 I/O 细节。
- Camera 请求触发的媒体降级不会因 Adapter 改为 DEBUG 而在默认级别静默。
- 对账、退避、取消和敏感数据测试全部通过。
- 相关设计文档与实际事件和级别一致。

## 与下一任务的衔接信息

任务 3 使用任务 1 的日志入口和本任务的事件字段风格实现 HTTP access log。交接时记录：

- 最终事件名、组件名和字段名称。
- 持续故障状态放置位置及 30 分钟提醒规则。
- `caplog` 断言结构化字段的测试示例。

任务 3 不得复用 Uvicorn 原始 `request_line`，其中可能包含 query string。
