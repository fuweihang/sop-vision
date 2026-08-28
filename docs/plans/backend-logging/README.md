# Backend Logger 打印风格重设计

## 计划状态

- 状态：待实施
- 创建日期：2026-08-28
- 影响范围：`backend/`、Backend 的 Compose/环境变量和相关设计文档
- 执行方式：按 `01` → `02` → `03` → `04` 顺序完成，每个任务单独实现、验证和审核
- 明确不影响：HTTP API、OpenAPI、数据库结构、前端行为、媒体对账算法和重试时间

## 拆分原因

这项工作同时跨越日志基础设施、业务事件、HTTP/Uvicorn、SQLAlchemy/Alembic 和部署入口。后续任务
依赖前一任务实际交付的字段、Formatter 和启动方式，不适合在一次实现中完成。

拆分后的任务分别提供以下可独立验证的交付物：

1. 所有运行时 Logger 共用的日志基础和启动入口。
2. 简短业务事件、持续故障降噪和恢复日志。
3. 带 trace 和耗时、且不记录 query 的应用级 HTTP access log。
4. 统一的 SQLAlchemy/Alembic 输出和 Backend 全量验证。

## 当前问题

- Uvicorn 默认配置主要处理 `uvicorn.*` Logger，`app.*` 告警可能只显示裸 `message`。
- Backend 原本缺少一个能同时控制 Uvicorn 与 `app.*` Logger 的日志级别配置。
- MediaMTX Adapter 和对账 Runner 把相同字段同时写入 `message` 与 `extra`。
- 缺失字段仍显示为 `trace_id=-`、`source_id=-`，无意义的零计数占用主要位置。
- 同一次 MediaMTX 故障由 Adapter 和 Runner 各打印一条 WARNING，并在持续故障时反复出现。
- `TraceIdLogFilter` 已存在，但没有安装到统一 Handler。
- Camera 完整性日志的关键 ID 只放在 `extra`，当前控制台格式看不到。
- SQLAlchemy `echo=True` 可能和显式 logging 配置重复输出；Alembic 使用另一套格式。

## 目标输出

默认 console 格式：

```text
2026-08-28 16:31:12 WARN  media.reconciliation  MediaMTX 不可用，本轮对账已跳过  result=gateway_unavailable retry=257.0s failures=1 duration=5ms
2026-08-28 16:48:45 INFO  media.reconciliation  MediaMTX 已恢复，对账完成  result=success desired=4 managed=4 ensured=1 released=0 failures=7 degraded=1033.1s duration=12ms
2026-08-28 16:49:01 INFO  http.access           HTTP 请求完成  method=GET path=/api/v1/cameras status=200 result=completed duration=18ms trace=tr_abc123
2026-08-28 16:49:08 WARN  camera.create         Camera 已保存，但媒体操作未全部成功  result=degraded camera=... failed=2 trace=tr_abc123
2026-08-28 16:50:22 ERROR camera.integrity      Camera 引用完整性异常  kind=ORPHAN_SOURCE camera=... source=...
```

同时支持可选的 `BACKEND_LOG_FORMAT=json`。console 和 JSON 必须消费同一个 `LogRecord`，业务代码不能
为不同格式拼两套内容。

对应 JSON 示例：

```json
{"timestamp":"2026-08-28 16:31:12","level":"WARN","logger":"app.modules.cameras.application.reconciliation","component":"media.reconciliation","message":"MediaMTX 不可用，本轮对账已跳过","event":"media_reconciliation.round_failed","outcome":"gateway_unavailable","retry_in_seconds":257.0,"consecutive_failures":1,"duration_ms":5}
```

## 全局日志规则

### 显示规则

- 时间根据 Backend 进程的 `TZ` 格式化为 `YYYY-MM-DD HH:mm:ss`；容器默认使用
  `Asia/Shanghai`，不显示毫秒、时区偏移或缩写。
- console 前缀固定为 `timestamp level component message`；level 宽度为 5，组件列最小宽度为 22，
  长组件不截断。
- console level 固定显示为 `DEBUG/INFO/WARN/ERROR/CRIT`。
- 组件使用下方固定映射；原始 `record.name` 只进入 JSON 的 `logger` 字段。
- 应用自有的人可读 message 使用简体中文，稳定事件、操作和结果使用英文标识；Uvicorn、SQLAlchemy
  和 Alembic 的第三方 message 保留原文，只统一前缀、单行转义和安全异常栈。
- console 按事件表顺序输出字段，并使用下方短键；毫秒和秒分别补 `ms`、`s`，JSON 保持原字段名
  和数值类型。
- console 秒值固定保留一位小数，毫秒和计数使用整数；`error_frames` 使用逗号连接。JSON level 使用
  与 console 相同的 `DEBUG/INFO/WARN/ERROR/CRIT`，秒值保持原始数值，不转成字符串。
- Formatter 统一省略 `None`、空字符串和 `-`。数值 `0` 是否有意义由事件调用方决定：调用方只附加
  事件表要求的字段，Formatter 不自行猜测或删除 `0`。
- console 必须把换行、制表符、其他 C0 控制字符和 DEL 转义为可见文本，保证一个 LogRecord 只占
  一行；JSON 使用紧凑单行编码并保留中文。
- console 始终给日志级别输出 ANSI 颜色，不检测 TTY；终端、Docker 和采集器收到同一份带转义码的
  日志，采集端需要支持 ANSI 才能正确显示颜色。

### 组件映射

Formatter 按最长 Logger 前缀匹配；未命中时，`app.` Logger 去掉 `app.` 前缀，其他 Logger 保留
完整名称。调用方不得通过 `extra` 覆盖组件。

| Logger 或前缀 | component |
| --- | --- |
| root | `backend` |
| `app.factory` | `backend.lifecycle` |
| `app.modules.stream_gateway.services.mediamtx` | `stream.gateway` |
| `app.modules.cameras.application.reconciliation` | `media.reconciliation` |
| `app.modules.cameras.application.create` | `camera.create` |
| `app.modules.cameras.persistence.integrity` | `camera.integrity` |
| `app.core.http.access` | `http.access` |
| `uvicorn.access` | `server.access`，任务 3 后停用 |
| `uvicorn`、`uvicorn.error` | `server` |
| `sqlalchemy.engine` | `database.sql` |
| `alembic` | `database.migration` |

### 公共字段

| 字段 | 来源 | 说明 |
| --- | --- | --- |
| `timestamp` | Formatter | 根据 `record.created` 和进程 `TZ` 生成地区时间 |
| `level` | LogRecord | 日志级别 |
| `logger` | LogRecord | 完整 Logger 名 |
| `component` | Formatter | 根据 Logger 名映射，调用方不得任意填写 |
| `message` | 调用方 | 简短中文说明，不拼接任意对象或异常文本 |
| `event` | 调用方 | 稳定英文事件名 |
| `trace_id` | Handler Filter | 从 HTTP ContextVar 读取，没有时省略 |
| `error_frames` | 安全异常 helper / Formatter | 未知异常的安全帧列表，普通事件省略 |

允许的第一批事件字段：

- 通用：`operation`、`outcome`、`duration_ms`、`error_type`、`error_frames`
- ID：`camera_id`、`source_id`
- Adapter：`path_count`
- 对账：`desired_count`、`managed_path_count`、`ensured_count`、`released_count`、
  `failed_count`、`retry_in_seconds`、`consecutive_failures`、`degraded_duration_seconds`
- 完整性：`integrity_issue_kind`
- HTTP：`method`、`path`、`status_code`
- 生命周期：`timeout_seconds`

Formatter 不得自动展开未知 `extra`。新增字段必须同步更新白名单和测试。

字段类型固定为：ID、event、operation、outcome、error type、method 和 path 使用字符串；
`error_frames` 使用字符串数组；`duration_ms`、`status_code` 和全部 count 使用非负整数；秒字段使用
非负数值。业务调用必须在写入 LogRecord 前完成 UUID/Enum 到稳定字符串的转换。

JSON 顶层键顺序固定为 `timestamp/level/logger/component/message/event/trace_id`，随后按事件表顺序
输出事件字段。没有 `event` 的 Uvicorn、SQLAlchemy 和 Alembic 记录仍输出前五个公共字段。

console 不重复显示 `logger` 和 `event`；稳定事件由 JSON 或 LogRecord 字段提供。console 短键固定为：

| 结构字段 | console 短键 |
| --- | --- |
| `operation`、`outcome` | `operation`、`result` |
| `duration_ms` | `duration` |
| `error_type`、`error_frames` | `error`、`frames` |
| `camera_id`、`source_id` | `camera`、`source` |
| `path_count` | `paths` |
| `desired_count`、`managed_path_count` | `desired`、`managed` |
| `ensured_count`、`released_count`、`failed_count` | `ensured`、`released`、`failed` |
| `retry_in_seconds`、`consecutive_failures` | `retry`、`failures` |
| `degraded_duration_seconds` | `degraded` |
| `integrity_issue_kind` | `kind` |
| `method`、`path`、`status_code` | `method`、`path`、`status` |
| `timeout_seconds`、`trace_id` | `timeout`、`trace` |

### 第一批事件

表中字段顺序同时是 console 和 JSON 的事件字段顺序。未列出的字段不得附加到该事件。

| event | 固定 message | 级别 | 字段与出现条件 |
| --- | --- | --- | --- |
| `stream_gateway.io` | `MediaMTX 调用完成` 或 `MediaMTX 调用失败` | 始终 `DEBUG` | `operation,outcome,duration_ms`；失败时加 `error_type`；单 Source 操作加 `source_id`；成功快照加 `path_count` |
| `media_reconciliation.round_completed` | `媒体对账完成` 或 `未取得对账锁，本轮已跳过` | 无变更/锁竞争 `DEBUG`，有 ensure/release `INFO` | `outcome`；成功时加 `desired_count,managed_path_count`；有变更时再加 `ensured_count,released_count`；最后加 `duration_ms` |
| `media_reconciliation.round_failed` | 见下方 outcome 消息表 | 首次、outcome 变化、30 分钟提醒为 `WARNING`，其余 `DEBUG` | `outcome`；仅 `partial_failure` 加五个计数字段；随后加 `retry_in_seconds,consecutive_failures`；降级时间大于 `0` 时加 `degraded_duration_seconds`；最后加 `duration_ms` |
| `media_reconciliation.recovered` | 根据最后一个失败 outcome 使用下方恢复消息 | `INFO` | `outcome,desired_count,managed_path_count,ensured_count,released_count,consecutive_failures,degraded_duration_seconds,duration_ms`；ensure/release 即使为 `0` 也保留 |
| `media_reconciliation.runner_exit` | `媒体对账任务停止异常` | `ERROR` | `outcome`；超时时加 `timeout_seconds`；有安全异常栈时加 `error_type,error_frames` |
| `camera.media_sync_degraded` | `Camera 已保存，但媒体操作未全部成功` | `WARNING` | `operation=post_commit_media_sync,outcome=degraded,camera_id,failed_count` |
| `camera.reference_integrity_failed` | `Camera 引用完整性异常` | `ERROR` | `integrity_issue_kind,camera_id`；有 Source 时加 `source_id` |
| `http.request_completed` | 根据 outcome 使用 `HTTP 请求完成`、`HTTP 请求处理失败` 或 `HTTP 响应发送中断` | `completed` 的 100–499 为 `INFO`、500–599 为 `ERROR`；`failed/response_interrupted` 始终为 `ERROR` | `method,path,status_code,outcome,duration_ms`；trace 由 Filter 增加 |

HTTP outcome 固定规则：

| outcome | 使用条件 | status_code |
| --- | --- | --- |
| `completed` | 最后一个响应正文消息已成功发送，包括完整的 4xx/5xx 响应 | 实际发送状态 |
| `failed` | 响应头发送前发生未处理异常 | 现有 ServerError 将生成的 `500` |
| `response_interrupted` | 响应头已发送、正文未完整发送时发生未处理异常 | 已发送的真实状态，不得改写成 `500` |

正文已经完整发送并记录 `completed` 后再发生异常时，不生成第二条 access log；异常继续由现有
ServerError/Uvicorn 错误日志报告。HTTP access log 不记录异常类型、异常文本或堆栈。

对账失败 message 固定映射：

| outcome | message |
| --- | --- |
| `partial_failure` | `部分媒体路径处理失败` |
| `database_error` | `数据库不可用，本轮对账已跳过` |
| `gateway_unavailable` | `MediaMTX 不可用，本轮对账已跳过` |
| `gateway_invalid_response` | `MediaMTX 响应无效，本轮对账已跳过` |
| `unexpected_error` | `媒体对账发生未知错误` |

恢复 message 根据故障状态中最后一个失败 outcome 固定映射：`gateway_unavailable` 和
`gateway_invalid_response` 使用 `MediaMTX 已恢复，对账完成`，`database_error` 使用
`数据库已恢复，对账完成`，`partial_failure` 和 `unexpected_error` 使用 `媒体对账已恢复`。

### Logger 级别

通过 `app.server` 启动的 Backend 记录最终进入同一个 level=`NOTSET` 的 `stderr` Handler，级别只由
下表 Logger 决定；已列 Logger 不保留自己的 Handler，避免重复输出。pytest 或嵌入式宿主已有
Handler 时必须保留，由对应任务的测试单独验证。
所有已列非 root Logger 使用 `propagate=True`；不得同时传播并挂自己的输出 Handler。

| Logger | 级别规则 |
| --- | --- |
| root | 固定 `WARNING`，阻止未列出的第三方 DEBUG/INFO 噪声 |
| `app` | 跟随 `BACKEND_LOG_LEVEL` |
| `uvicorn`、`uvicorn.error` | 跟随 `BACKEND_LOG_LEVEL` |
| `uvicorn.access` | 任务 1 跟随 `BACKEND_LOG_LEVEL`，任务 3 禁用 |
| `httpx`、`httpcore` | 固定 `WARNING`，不得因 Backend DEBUG 输出请求细节 |
| `sqlalchemy` | 任务 1–3 固定 `WARNING`；任务 4 改为 `DATABASE_ECHO=true` 时 `INFO`，否则 `WARNING` |
| `alembic` | 独立迁移命令为 `INFO`；嵌入已有进程时服从宿主 Handler，只调整 Alembic Logger 级别 |

### 分级和降噪

| 场景 | 默认行为 |
| --- | --- |
| Adapter 单次 I/O | `DEBUG` |
| 对账成功但无变更、锁竞争 | `DEBUG` |
| 对账实际 ensure/release | `INFO` |
| 首次失败、失败类型变化 | `WARNING` |
| 相同故障持续 | `DEBUG`，每 30 分钟补一条 `WARNING` |
| 故障恢复 | `INFO` |
| Camera 提交后媒体操作未全部成功 | 每个请求一条 `WARNING` |
| Runner 停止超时、异常退出 | `ERROR` |
| Camera 引用完整性异常 | `ERROR` |
| 完整发送的 HTTP 100–499 | `INFO`，`outcome=completed` |
| 完整发送的 HTTP 500–599 | `ERROR`，`outcome=completed` |
| 响应头发送前发生未处理异常 | `ERROR`，`status_code=500/outcome=failed` |
| 响应头已发送、正文未完成时发生未处理异常 | `ERROR`，保留真实 status，`outcome=response_interrupted` |
| 成功的 live/ready 探针 | `completed` 且状态为 200–399 时不输出；其他结果仍输出 |

### 安全规则

- 不记录 Camera 用户名、密码、Source 后缀和完整 RTSP URL。
- 不记录 MediaMTX 原始响应、请求正文或异常字符串。
- HTTP access log 只记录 path，禁止记录 query string、headers 和 body。
- SQLAlchemy 始终启用 `hide_parameters=True`。
- 已知错误只记录稳定 `error_type/outcome`，不使用 `logger.exception()`。
- 应用未知错误使用固定 message，并通过统一 helper 从异常生成纯字符串 `error_type/error_frames`；
  LogRecord 不保存异常对象、异常文本或原始 `exc_info`。
- Uvicorn 等第三方 Logger 自带 `exc_info` 时，Formatter 忽略原始异常文本、`exc_text` 和
  `stack_info`，只生成 `error_type` 与最多 20 个最内层 `文件名:函数:行号` 到 `error_frames`；不记录
  绝对路径、局部变量和源代码行。
- console 和 JSON 使用相同字段白名单。

## 执行任务

1. [01｜统一日志基础与 Backend 启动入口](./01-logging-foundation.md)
2. [02｜业务日志事件改造与持续故障降噪](./02-business-events-and-noise-reduction.md)
3. [03｜应用级 HTTP Access Log 与 Uvicorn 去重](./03-http-access-logging.md)
4. [04｜SQLAlchemy/Alembic 接入、文档和全量验证](./04-database-migration-and-release.md)

推荐首先执行任务 1。每个任务完成后应提交其验证结果，再开始下一任务。

## 最终影响范围

预计新增：

- `backend/src/app/core/logging.py`
- `backend/src/app/server.py`
- `backend/src/app/core/http/access.py`
- `backend/tests/core/test_logging.py`
- `backend/tests/test_server.py`

预计修改：

- `backend/src/app/core/config.py`
- `backend/src/app/core/http/trace.py`
- `backend/src/app/core/http/__init__.py`
- `backend/src/app/factory.py`
- `backend/src/app/modules/stream_gateway/services/mediamtx.py`
- `backend/src/app/modules/cameras/application/reconciliation.py`
- `backend/src/app/modules/cameras/application/create.py`
- `backend/src/app/modules/cameras/persistence/integrity.py`
- `backend/src/app/core/database/engine.py`
- `backend/migrations/env.py`
- `backend/alembic.ini`
- `backend/Dockerfile`、`compose.yaml`、环境变量示例和 Backend README
- 根 `README.md` 与 `AGENTS.md` 中的 Backend 启动命令
- 上述模块的对应测试及相关 Cameras MVP 文档

日志文本属于有意的破坏性变更。依赖原始 `operation=... outcome=...` 文本的采集规则、正则和告警需要
改为启用 JSON，并读取其中的 `event` 与稳定字段；默认 console 只面向人工查看，不承诺整行解析兼容。
