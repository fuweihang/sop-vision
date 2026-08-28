# Backend 日志

Backend 使用 Python 标准库 `logging` 统一处理应用、Uvicorn、SQLAlchemy 和 Alembic 输出。业务代码
只创建一个 `LogRecord`；同一条记录可以按面向终端的 console 格式或面向采集器的 JSON 格式写到
`stderr`，不在业务代码中分别拼接两套消息。

详细规则：

- [事件与级别](events.md)：组件名、稳定事件、允许字段和降噪规则。
- [HTTP access log](http-access.md)：记录时机、结果分类和敏感数据边界。
- [数据库与迁移日志](database.md)：`DATABASE_ECHO`、SQL 参数保护和 Alembic 行为。
- [决策 0002](../../decisions/0002-backend-structured-logging.md)：选择统一结构化事件和安全输出边界的原因。

## 输出链路

```text
应用或第三方 Logger
        ↓ LogRecord
统一 stderr Handler
        ↓ TraceIdLogFilter（存在请求上下文时补 trace_id）
console 或 JSON Formatter
        ↓
终端 / Docker 日志 / 部署侧采集器
```

Runtime 通过 `python -m app.server` 启动。该入口先加载配置和安装日志 Handler，再把同一份
`log_config` 交给 Uvicorn；reload 和多 worker 子进程因此使用相同格式。pytest 或嵌入式宿主已安装
的 Handler 会被保留，重复初始化不会重复添加 Backend Handler。

本能力不提供文件轮转、远端上传、日志留存、审计日志或指标系统。这些工作应由部署环境完成，并
读取 JSON 的稳定字段，不应从 console 整行文本提取数据。

## 配置

| 环境变量             | 默认值          | 行为                                                              |
| -------------------- | --------------- | ----------------------------------------------------------------- |
| `BACKEND_LOG_LEVEL`  | `info`          | 控制 `app.*` 与 Uvicorn；支持 `debug/info/warning/error/critical` |
| `BACKEND_LOG_FORMAT` | `console`       | `console` 输出人读单行；`json` 输出单行 JSON                      |
| `DATABASE_ECHO`      | `false`         | 单独控制普通 SQL 是否通过 `database.sql` 输出                     |
| `TZ`                 | `Asia/Shanghai` | 控制日志时间显示地区，使用 IANA 时区名称                          |

`BACKEND_LOG_LEVEL=debug` 不会打开 SQLAlchemy、httpx 或 httpcore 的调试输出。查看 SQL 必须单独设置
`DATABASE_ECHO=true` 并重启 Backend 或容器。

console 示例：

```text
2026-08-28 16:48:45 INFO  media.reconciliation  MediaMTX 已恢复，对账完成  result=success desired=4 managed=4 ensured=1 released=0 failures=7 degraded=1033.1s duration=12ms
2026-08-28 16:49:01 INFO  http.access           HTTP 请求完成  method=GET path=/api/v1/cameras status=200 result=completed duration=18ms trace=tr_abc123
```

console 的级别列包含 ANSI 颜色，适合人工阅读。采集器应使用 JSON：

```json
{
  "timestamp": "2026-08-28 16:49:01",
  "level": "INFO",
  "logger": "app.core.http.access",
  "component": "http.access",
  "message": "HTTP 请求完成",
  "event": "http.request_completed",
  "trace_id": "tr_abc123",
  "method": "GET",
  "path": "/api/v1/cameras",
  "status_code": 200,
  "outcome": "completed",
  "duration_ms": 18
}
```

`timestamp` 按进程 `TZ` 输出 `YYYY-MM-DD HH:mm:ss`，不附带毫秒或时区偏移。该设置只影响日志展示；
数据库、API 和媒体快照仍按各自规则使用 UTC。

## 公共规则

- 应用 message 使用简短中文；`event`、`operation`、`outcome` 等机器字段使用稳定英文值。
- `component` 由 Logger 名映射，业务调用方不能自行覆盖；JSON 额外保留完整 `logger` 名。
- trace 只由统一 Filter 从请求上下文读取。非 HTTP 日志直接省略，不输出 `trace=-`。
- Formatter 只输出白名单字段；`None`、空字符串和 `-` 被省略。数值 `0` 是否有意义由事件调用方
  决定，Formatter 不自行删除。
- console 会转义换行、制表符、C0 控制字符和 DEL；每个 LogRecord 只占一个物理行。JSON 同样是
  紧凑单行，并保留中文和数值类型。
- 第三方异常只保留异常类型和最多 20 个最内层 `文件名:函数:行号`。不得记录异常文本、绝对路径、
  局部变量或源码行；应用未知异常使用统一安全 helper，不能改回 `logger.exception()`。
- 不记录密码、Token、数据库连接串、完整 RTSP URL、MediaMTX 原始响应、HTTP query、headers、
  body、客户端 IP 或 User-Agent。

## 修改日志时

新增事件或字段时，需要同时修改事件白名单、console 短键、调用方和 Formatter 测试。不要把任意对象
放进 `extra`，也不要依赖完整中文 message 或 JSON 键顺序做自动化判断。业务影响应由 Application
层以合适级别记录；外部 Adapter 的单次 I/O 通常只保留 DEBUG 诊断。

新增 Logger 时先判断它是否需要固定 `component`。没有映射的 `app.*` Logger 会去掉 `app.` 前缀，
其他第三方 Logger 保留原名。Logger 不应同时拥有输出 Handler 又向 root 传播，否则同一记录会打印
两次。

## 排障

- 看不到应用 INFO：确认 `BACKEND_LOG_LEVEL`，并确认进程由 `python -m app.server` 启动。
- 看不到 SQL：确认 `DATABASE_ECHO=true` 且已重启；`BACKEND_LOG_LEVEL=debug` 不会替代该开关。
- 同一请求出现两条 access log：检查是否绕过 `app.server` 重新启用了 Uvicorn access log。
- JSON 缺少业务字段：确认事件已在白名单中、字段类型正确，且值不是空字符串或 `-`。
- 后台任务没有 trace：这是预期行为；只有绑定了 HTTP 请求上下文的记录才包含 `trace_id`。

## 验证

```bash
cd backend
uv run pytest tests/core/test_logging.py \
  tests/core/http/test_http_foundation.py \
  tests/core/database/test_engine.py \
  tests/core/database/test_migrations.py \
  tests/test_server.py tests/test_config.py
uv run ruff check .
uv run ruff format --check .
```

迁移集成测试需要在 `backend/.env.local` 配置独立 `TEST_DATABASE_URL` 后使用
`uv run --env-file .env.local pytest ...`；测试被跳过时不能视为迁移路径已验证。
