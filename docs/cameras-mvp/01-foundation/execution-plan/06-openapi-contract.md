# 步骤 6｜公共 Schema 与 OpenAPI

> 前置：[步骤 3](./03-domain-model.md)、[步骤 5](./05-http-foundation.md)  
> 产出：覆盖 Cameras MVP 的 Pydantic Schema、确定性 OpenAPI 和契约测试

## 1. 完成目标

把 `01-foundation` 与 `02–09` 已冻结的 HTTP 数据形状编译为唯一后端 Schema 来源，为后续路由和前端类型生成提供稳定契约。本步骤定义数据结构但不实现业务 handler。

## 2. Schema 清单

至少覆盖：

- `FieldError`、`ProblemDetails`。
- canonical Camera/Source UUID 字段和 RFC 3339 UTC 时间。
- `CameraCreateRequest`、`CameraUpdateRequest`、Source create/update item。
- `CameraDetail`、`CameraSourceDetail`。
- `CameraSummary`、默认源摘要、`CameraPage`。
- 默认预览源变更请求/响应。
- `SourceStatusSummary`、Camera/Source 状态枚举与稳定 error code。
- `PlaybackInfo` 及 WHEP 协议/可用状态。
- 分页、404、409、422、502、503 等已声明响应组件。

请求模型统一 `extra="forbid"`；只读字段不能被请求模型接受。列表响应不得复用包含凭据的详情模型。

## 3. OpenAPI 规则

- 契约产物固定写入 `contracts/openapi.json`，由代码生成，不手工编辑。
- 输出排序和序列化必须确定，连续生成内容一致。
- UUID 是 `type: string, format: uuid`；枚举为冻结的大写英文值。
- 每个 Schema 包含与功能文档一致且经过模型校验的 example。
- Cameras 路由未来只使用 `cameras` 与 `camera-sources` tags；现有非 Cameras 路由可保留自己的 tag。
- 每个实际路由必须显式设置稳定唯一 `operation_id`。
- Foundation 尚无业务路由时，通过确定性的 OpenAPI component registry 注册公共 Schema；禁止创建伪造、隐藏或不可调用的业务端点只为暴露类型。

## 4. 契约边界检查

- `CameraSummary` 不含 `username/password/url_suffix/rtsp_url`。
- `PlaybackInfo` 不含 Camera 凭据或 RTSP 上游信息。
- `CameraDetail` 明确包含敏感字段，后续路由必须配套 `Cache-Control: no-store`。
- Source 顺序使用数组表达，不暴露 `sort_order` 为客户端可写字段。
- 创建请求不接受 `source_id`；更新请求只在已有 Source item 中可选接受 `source_id`。
- 错误响应始终引用同一个 Problem Schema，不为每条路由复制近似模型。

## 5. 实施顺序

1. 从功能文档建立 Schema/operation/error 对照表，消除命名重复。
2. 实现 Pydantic 请求、响应和枚举模型。
3. 为每个 example 添加 `model_validate` 测试。
4. 实现确定性 OpenAPI 导出命令和 component registry。
5. 对 operation ID、tag、响应 media type 和敏感字段边界做结构化测试。
6. 提交生成的 `contracts/openapi.json`，并记录生成命令。

## 6. 必测场景

- 所有功能文档 JSON example 都能被对应 Schema 接受。
- 未知请求字段、非法 UUID、非法枚举和只读字段被拒绝。
- OpenAPI 连续生成两次字节一致。
- operation ID 全局唯一；已注册错误使用 `application/problem+json`。
- 列表与 Playback Schema 的敏感字段黑名单测试通过。
- 删除响应在契约中为 `204` 且无响应 body。

## 7. 退出条件

- Backend Schema 是手写契约的唯一代码来源，OpenAPI 是生成产物。
- 现有早期 `stream_gateway/schemas/camera.py` 已删除或迁移，无法与新契约并存。
- 新契约尚未声称 Camera 业务路径已可调用。
- 后续路由只需引用现有 Schema 和公共 response component，无需重新定义 DTO。

## 8. 后续交接

步骤 7 只从 `contracts/openapi.json` 生成 TypeScript 类型。后续功能切片若修改 Schema，必须先更新后端模型、重新生成 OpenAPI，并通过步骤 9 的漂移检查。
