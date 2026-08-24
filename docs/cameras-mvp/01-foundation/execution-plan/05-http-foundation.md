# 步骤 5｜HTTP 公共机制

> 前置：[步骤 3](./03-domain-model.md) 的错误 code 与字段路径约定  
> 产出：trace ID、Problem Details、框架异常转换、严格 UUID、分页/搜索依赖

## 1. 完成目标

让后续 Camera 路由只声明业务成功和业务错误，不再重复实现错误媒体类型、字段路径、trace ID、UUID 或分页参数校验。

## 2. 公共组件

建议放置于 `app/core/http/` 和 `app/modules/cameras/api/`：

- `TraceIdMiddleware`：为每个响应设置 `X-Trace-Id`，并把同一值注入 request state 和 Problem body。
- `ProblemDetails`、`FieldError` 及 `application/problem+json` 响应工厂。
- `RequestValidationError`、Starlette HTTP error、领域错误和已知依赖错误的异常处理器。
- 严格 canonical UUID v4 参数类型：仅接受小写、带连字符标准文本。
- Camera 列表参数依赖：`page/page_size/q` 的默认值和规范化。
- Pydantic/FastAPI location 到 `sources[1].url_suffix` 形式的字段路径转换器。

## 3. trace ID 规则

- 若入口提供受信且符合长度/字符白名单的 `X-Trace-Id`，可透传；否则生成新值。
- 成功和错误响应都返回 header；Problem body 的 `trace_id` 必须相同。
- 日志只从 request context 读取，不允许各层自行生成不同 ID。
- `instance` 只包含请求 path，不含可能携带敏感信息的 query value。

## 4. 错误转换规则

- 所有结构化错误使用 `application/problem+json`。
- Problem `type` 固定为 `urn:sop-vision:problem:<kebab-case-code>`，由稳定错误 code 推导；
  不使用服务 IP、虚构域名或随环境变化的 Base URL，也不要求客户端解析或访问该 URN。
- 前端分支只依赖 `status/code/errors[].field/errors[].code/context`。
- 未知字段映射为 `UNKNOWN_FIELD`，缺失、长度、范围、UUID 等使用 Foundation 稳定 code。
- 路径 UUID、请求体 UUID 和查询字段错误统一返回 `422 VALIDATION_ERROR`。
- 处理器不得把 Pydantic 原始 input、数据库异常文本、密码或完整 RTSP URL放入 `detail/context/errors`。
- 已知 404/409/502/503 只建立公共映射能力；Foundation 不创建触发这些业务错误的 Camera 路由。

## 5. 分页与搜索

- `page >= 1`，`1 <= page_size <= 100`。
- `q` trim，空白转 `None`，非空最长 100。
- 参数对象是不可变值，既供 Repository criteria 使用，也供前端 Query Key 契约使用。
- Camera 列表固定按 `created_at ASC, camera_id ASC`，参数对象不包含排序字段。
- 额外查询参数（包括旧的 `sort`）按 FastAPI 默认行为忽略；它们不进入 OpenAPI、参数对象或
  Query Key，也不改变固定顺序。非法字段错误准确指向 `page`、`page_size` 或 `q`。

## 6. 实施顺序

1. 实现 Problem/FieldError Schema 和安全响应工厂。
2. 实现 trace middleware 及日志上下文。
3. 实现框架异常转换和字段路径转换。
4. 实现 canonical UUID v4 类型。
5. 实现分页和搜索依赖。
6. 用仅存在于测试中的 probe router 覆盖所有行为；不添加 Camera 业务路由。
7. 将现有 FastAPI 默认 422 和已声明 HTTP 错误纳入统一 Problem 行为。

## 7. 必测场景

- 成功与错误响应的 trace header/body 一致；恶意或超长入口 ID 被替换。
- 大写、无连字符、花括号、非 v4 UUID 均返回 `INVALID_UUID`。
- `sources[1].name` 等嵌套数组路径精确转换。
- 非法 page/page_size 和超长 q 返回精确字段错误；额外查询参数被忽略。
- 仅空白 q 规范化为未提供。
- 未知 JSON 字段返回 `UNKNOWN_FIELD`。
- 测试密码和完整 RTSP URL 不出现在响应与捕获日志。

## 8. 退出条件

- 测试 probe router 的所有错误均为 Problem JSON，且无 FastAPI 默认 `detail` 数组泄漏。
- 公共组件与 Cameras 业务错误解耦，可由后续路由显式声明。
- 现有健康路由仍可工作；Foundation 的 Cameras tag 限制不删除全局 `health` tag。
- 本步骤没有任何 Camera CRUD handler。

## 9. 后续交接

步骤 6 使用这些 Pydantic 公共模型生成 OpenAPI。后续功能路由必须显式声明稳定 `operation_id` 和可能响应，不能依赖未记录的框架默认响应。
