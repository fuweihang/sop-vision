# HTTP access log

Backend 用应用级 ASGI middleware 记录 HTTP 结果，并关闭 Uvicorn 原生 access log。每个请求在响应
完整发送或发生中断后最多输出一条 `http.request_completed`，这样状态码和耗时表示客户端实际收到的
结果，而不是请求刚进入应用时的预测状态。

异常诊断与 access log 分开：access log 只说明请求结果，不保存异常类型、文本或堆栈；未处理异常
继续由现有 ServerError/Uvicorn 错误日志报告。正文完整发送后又发生异常时，不补第二条 access log。

## 结果分类

| outcome                | 使用条件                                     | status_code      | 级别                              |
| ---------------------- | -------------------------------------------- | ---------------- | --------------------------------- |
| `completed`            | 最后一个响应正文消息已成功发送               | 实际发送状态     | 100–499 为 INFO，500–599 为 ERROR |
| `failed`               | 响应头发送前发生未处理异常                   | 500              | ERROR                             |
| `response_interrupted` | 响应头已发送、正文未完整发送时发生未处理异常 | 已发送的真实状态 | ERROR                             |

如果流式响应已经发送 `200` 响应头后中断，日志保留 `status_code=200`，同时用
`outcome=response_interrupted` 和 ERROR 表示响应不完整。把状态改成 500 会误导排障人员，因为客户端
已经收到的响应头无法撤回。

成功的 `/api/v1/health/live` 和 `/api/v1/health/ready` 在 `completed` 且状态为 200–399 时静默，减少
探针噪声；错误状态、处理失败和流式中断仍输出。

## 字段与安全

事件只包含 `method`、ASGI 已解析的 `path`、`status_code`、`outcome`、完整 `duration_ms`，以及统一
Filter 从请求上下文补充的 `trace_id`。

不得读取或记录 query string、请求/响应正文、headers、客户端 IP 或 User-Agent。只使用 `path` 也
避免 Uvicorn request line 把 query 中的临时凭据写入日志。

## 验证

```bash
cd backend
uv run pytest tests/contract/core/test_http_foundation.py \
  tests/module/core/test_health.py \
  tests/unit/core/test_server.py
```

测试覆盖普通响应、4xx/5xx、响应头前异常、流式中断、正文完成后异常、query 脱敏、控制字符单行
转义、探针静默、trace 关联和 access 去重。
