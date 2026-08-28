# 03｜应用级 HTTP Access Log 与 Uvicorn 去重

## 任务目标

由应用在 trace 上下文仍有效时记录一次 HTTP access log，包含 method、path、status、耗时和 trace；
禁用 Uvicorn 内置 access log，避免重复和 query string 泄漏。

## 当前上下文 / 前置条件

- 必须先完成任务 1 和 2，并阅读同目录 `README.md` 的安全规则。
- 任务 1 已提供 `http.access` 组件、Formatter 和自动 trace Filter。
- 当前 `TraceIdMiddleware` 是最外层 HTTP 中间件，并在请求结束时 reset ContextVar。
- CORS 先注册、Trace 后注册是有意的；新增 access 后仍须覆盖 CORS 预检和提前响应。
- Uvicorn 内置 access log 不能可靠读取应用 trace，并可能在 request line 中包含 query。

## 实施范围

新增或修改：

- `backend/src/app/core/http/access.py`
- `backend/src/app/core/http/__init__.py`
- `backend/src/app/core/logging.py`
- `backend/src/app/factory.py`
- `backend/src/app/server.py`
- `backend/tests/core/http/test_http_foundation.py`
- `backend/tests/core/test_logging.py`
- `backend/tests/test_server.py`
- `backend/README.md`
- `docs/modules/cameras/foundation.md`

HTTP 事件字段固定为：

- `event=http.request_completed`
- `message` 根据 `outcome` 固定为 `HTTP 请求完成`、`HTTP 请求处理失败` 或
  `HTTP 响应发送中断`
- `method`
- `path`
- `status_code`
- `outcome=completed|failed|response_interrupted`
- `duration_ms`
- `trace_id` 由统一 Filter 自动读取

三个 outcome 只描述应用看到的 HTTP 生命周期结果，不包含异常内容：

- `completed`：最后一个响应正文消息已成功发送，包括完整发送的 4xx/5xx 响应。
- `failed`：发送响应头前发生未处理异常；现有 ServerError 行为会生成 `500` 响应。
- `response_interrupted`：响应头已经发送，但正文尚未完整发送时发生未处理异常。

## 明确不做

- 不记录请求/响应正文、headers、query string、client IP 或 User-Agent。
- 不修改 Trace ID 的生成、传入校验和响应头规则。
- 不增加分布式追踪 SDK。
- 不增加请求开始日志；单条结束日志必须保留实际状态、完整耗时和最终 outcome。
- 不把 4xx 提升为 WARNING。
- 不改变 FastAPI 异常到 Problem Details 的响应行为。
- access log 不记录异常类型或堆栈；未处理异常继续交给现有 ServerError/Uvicorn 错误日志。

## 实施步骤

1. 实现纯 ASGI access middleware：
   - 只处理 `scope["type"] == "http"`。
   - 构造参数允许注入 monotonic clock，生产默认 `time.monotonic`，测试不依赖真实时间。
   - 包装 `send` 捕获 `http.response.start` 状态码。
   - 最后一个 `http.response.body` 发送后只记录一次；流式响应结束后再计算总耗时。
   - 使用单次记录标记防止“正文已结束后下游又抛错”等异常 ASGI 路径产生第二条 access log。
   - 响应头发送前发生未处理异常时，记录 `status_code=500/outcome=failed` 后继续抛出。
   - 响应头发送后、最后一个正文消息发送前发生未处理异常时，保留已经发送的真实状态码，记录
     `outcome=response_interrupted` 后继续抛出；例如已经发送 `200` 的流式响应不得伪造为 `500`。
   - 最后一个正文消息发送并记录 `outcome=completed` 后，下游又抛出异常时不记录第二条 access
     log；异常仍向外传播并由现有错误日志报告。
2. method 使用 `scope["method"]`，path 只使用 `scope["path"]`，完全忽略 `query_string`。
   Formatter 按任务 1 的规则转义 path 中的控制字符，不能产生伪造的新日志行。
3. `outcome=completed` 时，100–499 使用 `INFO`、500–599 使用 `ERROR`；`failed` 和
   `response_interrupted` 始终使用 `ERROR`。日志级别表达执行是否异常，`status_code` 始终表达实际
   已发送或将由现有 ServerError 生成的状态，二者不能互相改写。
4. `/api/v1/health/live` 和 `/api/v1/health/ready` 在 `outcome=completed` 且状态为 200–399 时不
   输出；4xx、5xx、`failed` 和 `response_interrupted` 仍输出。
5. 固定中间件顺序：Trace 最外层、Access 位于 Trace 内层、CORS 位于 Access 内层。这样 access
   记录时 trace 仍有效，且预检响应也能记录。
6. 在任务 1 的 HTTP 事件字段顺序中加入 `outcome`，固定为
   `method,path,status_code,outcome,duration_ms`；console 显示为 `result`，JSON 保留 `outcome`。
7. `app.server` 向 Uvicorn 传 `access_log=False`，并确保统一配置不再为 `uvicorn.access` 安装独立
   Handler；不能只提高级别后留下可被其他配置重新开启的第二条 access line。
8. 更新 HTTP Foundation 测试和文档。

## 验证方式

```bash
cd backend
uv run pytest \
  tests/core/http/test_http_foundation.py \
  tests/core/test_logging.py \
  tests/test_server.py \
  tests/api/test_health.py
uv run ruff check .
uv run ruff format --check .
```

必须覆盖：

- 普通成功、Problem 4xx、完整 5xx、CORS OPTIONS、正常流式响应和响应头发送前的未处理异常。
- 流式响应发送 `200` 响应头后、最后一个正文消息前抛出异常：只产生一条 `ERROR` access log，
  `status_code=200/outcome=response_interrupted`，不得伪造 `500`。
- 最后一个正文消息发送并记录 access log 后再抛出异常：access log 仍只有一条
  `outcome=completed`，异常继续向外传播并由现有错误日志报告。
- 对有响应头/Problem body 的成功和已处理错误，access record 的 trace 与两者完全一致；未处理异常
  继续向外传播时，断言错误记录使用异常抛出前仍有效的请求 trace，不额外改变现有 ServerError
  响应行为。
- 包含密码哨兵的 query 不出现在 message、字段、console 或 JSON。
- percent-encoded 换行等 path 输入在 console 中保持单行，在 JSON 中可独立解析。
- live/ready 完整返回 2xx/3xx 时没有日志；4xx、5xx、处理失败和响应中断仍有日志。
- 内置 Uvicorn access handler 已关闭，不会产生第二条请求日志。
- `tests/test_server.py` 断言传给 Uvicorn 的 `access_log=False`，真实 Uvicorn 人工检查再验证运行输出。

真实 Uvicorn 人工检查：

1. 请求带 query 的普通 API，只出现一条 access log。
2. 日志只显示 path，不显示 `?` 后内容。
3. access trace 与响应 `X-Trace-Id` 一致。
4. 连续健康检查不刷屏。

## 完成标准

- 每个 HTTP 请求最多一条 access log。
- 默认启动不再输出 Uvicorn 原生 access line。
- access log 包含 method、path、真实 status、outcome、duration 和有效 trace。
- 未处理异常不会把已经发送的 2xx 状态伪造为 500；`ERROR` 和 `outcome` 明确表示处理失败或响应
  中断。
- query string 和请求内容不会进入任何输出格式。
- CORS、错误响应和流式响应仍正确，现有 HTTP 契约没有变化。
- 本任务测试和静态检查通过。

## 与下一任务的衔接信息

任务 4 使用同一配置接入 SQLAlchemy 和 Alembic，并执行全量回归。交接时记录：

- 新增 middleware 的模块名和工厂安装顺序。
- Uvicorn access log 的关闭位置。
- HTTP event 名、三个 outcome、对应 message 和字段顺序。
- 流式响应及异常路径的测试入口。

任务 4 只能验证这些行为，不应重新设计 HTTP 中间件顺序。
