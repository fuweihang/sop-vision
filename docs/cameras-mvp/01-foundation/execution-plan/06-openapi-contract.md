# 步骤 6｜公共 Schema、占位 Router 与 OpenAPI

> 前置：[步骤 3](./03-domain-model.md)、[步骤 5](./05-http-foundation.md)  
> 产出：覆盖 Cameras MVP 的 Pydantic Schema、尚未实现的占位 Router、确定性 OpenAPI 和契约测试

## 1. 完成目标

把 `01-foundation` 与 `02–09` 已冻结的公共 HTTP 数据形状编译为唯一后端 Schema 来源，并把
全部 Cameras MVP 路径注册到真实 FastAPI 应用。Foundation 阶段允许这些路径尚未实现业务
行为：handler 直接抛出 `NotImplementedError`，只利用 FastAPI Router 元数据提前生成稳定的
路径、请求、成功响应、错误响应和 `operation_id`，供步骤 7 生成完整前端类型。

路径出现在 OpenAPI 中只表示目标契约已经声明，不表示接口在开发期间可调用。后续功能切片在
交付真实 handler 时原位替换 `NotImplementedError`，不创建第二套路由或 DTO。
不在 OpenAPI、前端类型或其他登记表中记录功能完成度；只检查原 handler 是否仍包含占位
`raise NotImplementedError`。

## 2. Schema 清单

至少覆盖：

- `FieldError`、`ProblemDetails`。
- canonical Camera/Source UUID 输入字段、UUID v4 响应字段和 RFC 3339 UTC 时间。
- `CameraCreateRequest`、`CameraUpdateRequest`、Source create/update item。
- `CameraDetail`、`CameraSourceDetail`。
- `CameraSummary`、默认源摘要、`CameraPage`。
- 默认预览源变更请求/响应。
- `SourceStatusSummary`、Camera/Source 状态枚举和 Source 状态错误枚举。
- `PlaybackInfo` 及 WHEP 协议/可用状态。
- `400/404/409/422/500/502/503` 使用的公共 Problem response 声明。

请求模型统一 `extra="forbid"`；只读字段不能被请求模型接受。列表响应不得复用包含凭据的
详情模型。公共 `ProblemDetails.code` 和 `FieldError.code` 保持可扩展字符串；Problem code、
字段错误 code 和 Source 状态错误 code 分别维护冻结清单，不能混成 Cameras 专用的全局枚举。

## 3. 路由与 operation ID

以下路径在本步骤注册到运行应用，路径均包含公共前缀 `/api/v1`：

| 方法 | 路径 | `operation_id` | tag | 目标成功响应 | 已声明业务错误 |
| --- | --- | --- | --- | --- | --- |
| `GET` | `/cameras` | `listCameras` | `cameras` | `200 CameraPage` | `422/503` |
| `POST` | `/cameras` | `createCamera` | `cameras` | `201 CameraDetail` | `422/503` |
| `GET` | `/cameras/{camera_id}` | `getCamera` | `cameras` | `200 CameraDetail` | `404/422/500/503` |
| `PUT` | `/cameras/{camera_id}` | `updateCamera` | `cameras` | `200 CameraDetail` | `404/422/503` |
| `PATCH` | `/cameras/{camera_id}/default-preview-source` | `setDefaultPreviewSource` | `cameras` | `200` 轻量结果 | `404/422/503` |
| `DELETE` | `/cameras/{camera_id}` | `deleteCamera` | `cameras` | `204` 无 body | `404/422/503` |
| `GET` | `/camera-sources/{source_id}/playback` | `getCameraSourcePlayback` | `camera-sources` | `200 PlaybackInfo` | `404/409/422/502/503` |

现有非 Cameras 路由可保留自己的 tag，但也必须使用显式、全局唯一的 operation ID。本步骤把
健康检查冻结为 `healthLiveness` 和 `healthReadiness`，并让 readiness 的运行时 `503` 在
OpenAPI 中引用公共 Problem response。

## 4. 占位 Router 语义

- 占位 Router 注册到正常 `create_app()`，因此开发环境、测试应用和 `/openapi.json` 使用同一
  路由树，不维护只供导出的第二个 FastAPI 应用。
- 占位 handler 使用最小函数体，直接 `raise NotImplementedError`。不为占位行为设计专用异常、
  稳定错误 code 或额外 HTTP response。
- 占位 handler 不声明业务 Service、Repository、数据库或 MediaMTX 依赖，避免仅为生成契约而
  提前装配未完成的业务层。
- Foundation 不保证占位接口被调用时的状态码、媒体类型、校验先后顺序或错误正文；当前全局
  异常边界可能把它表现为 `500`，该结果不属于公共契约。
- OpenAPI 只描述冻结的目标成功响应和业务错误，不把 `NotImplementedError` 的临时运行结果
  声明成客户端需要兼容的正式响应。
- 后端测试只检查 Router 注册和 `app.openapi()` 结构，不把占位接口的实际调用结果作为验收
  条件。前端、MSW 和业务页面也不得调用占位 Backend 来判断功能是否已经实现。

允许的占位形式保持直白，不提取公共占位 helper：

```python
@router.post(
    "",
    response_model=CameraDetail,
    status_code=201,
    operation_id="createCamera",
    responses=CREATE_CAMERA_RESPONSES,
)
async def create_camera(request: CameraCreateRequest):
    raise NotImplementedError
```

其他 operation 使用相同原则分别声明自己的参数与响应；不要为了消除这一行重复而增加抽象。

## 5. OpenAPI 与响应规则

- 契约产物固定写入 `contracts/openapi.json`，由注册 Router 的真实应用代码生成，不手工编辑。
- 导出命令使用固定契约元数据和隔离 Settings，不进入 lifespan、不连接 PostgreSQL 或
  MediaMTX，也不因部署环境中的 `APP_NAME`、URL 或凭据改变输出。
- JSON 固定使用 UTF-8、`sort_keys=True`、统一缩进和单个末尾换行；连续生成必须字节一致。
- UUID 是 `type: string, format: uuid`；枚举为冻结的大写英文值。
- Problem `type` 示例和运行时响应使用步骤 5 冻结的
  `urn:sop-vision:problem:<kebab-case-code>`，所有部署环境保持相同值。
- 每个顶层公共 API 请求/响应 Schema 包含与功能文档一致、且经过 `model_validate` 的 example；
  不要求为枚举、纯嵌套类型或 MediaMTX 原始协议示例重复添加 example。
- CameraDetail 顶层 example 是唯一允许在契约中包含明确测试凭据和完整测试 RTSP URL 的示例；
  真实密码、泄漏 sentinel 和部署地址不得进入生成产物。
- 创建 `201` 声明 `Location` 和 `Cache-Control: no-store`；详情/更新成功声明
  `Cache-Control: no-store`；Playback `409` 声明 `Retry-After`；所有响应声明
  `X-Trace-Id`。
- 所有结构化错误只声明 `application/problem+json`。不能因 FastAPI 默认行为额外生成近似的
  `application/json` 错误模型。
- 每个实际路由显式设置稳定唯一 `operation_id`，禁止依赖函数名自动生成。

## 6. 契约边界检查

- `CameraSummary` 不含 `username/password/url_suffix/rtsp_url`。
- `PlaybackInfo` 不含 Camera 凭据或 RTSP 上游信息。
- `CameraDetail` 明确包含敏感字段，目标成功响应必须配套 `Cache-Control: no-store`。
- Source 顺序使用数组表达，不暴露 `sort_order` 为客户端可写字段。
- 创建请求不接受 `source_id`；更新请求可省略已有 Source item 的 `source_id`，但显式 `null`
  不表示已有 Source。
- 错误响应始终引用同一个 Problem Schema，不为每条路由复制近似模型。
- OpenAPI 只表达目标 HTTP 契约；调用方不能把路径出现在 OpenAPI 中当成业务已经完成，也不能
  依赖占位 handler 的临时失败形状。

## 7. 实施顺序

1. 从功能文档建立 Schema/operation/error/header 对照表，冻结本文件中的 operation ID。
2. 实现 Pydantic 请求、响应和枚举模型。
3. 为每个顶层公共 API example 添加 `model_validate` 测试。
4. 实现直接抛出 `NotImplementedError` 的 Cameras 与 CameraSource 占位 Router，并注册到正常
   应用工厂。
5. 为 health 和 Cameras 路由补齐显式 operation ID、响应头和媒体类型。
6. 实现不进入 lifespan 的确定性 OpenAPI 导出命令。
7. 提交 `contracts/openapi.json`，并记录生成命令。

## 8. 必测场景

- 所有公共 API JSON example 都能被对应 Schema 接受。
- 未知请求字段、非法 UUID、非法枚举和只读字段被拒绝。
- OpenAPI 连续生成两次字节一致，且生成过程不连接数据库或 MediaMTX。
- operation ID 全局唯一，tag、目标响应、响应头和 Problem media type 与本文件矩阵一致。
- 七个 Cameras operation 的路径和契约元数据均存在，且没有把临时 `NotImplementedError`
  声明成正式响应。
- 列表与 Playback Schema 的敏感字段黑名单测试通过。
- DELETE 的目标成功响应为 `204` 且无 body；不要求占位期实际调用得到该成功响应。

## 9. 退出条件

- Backend Router 与 Schema 是手写契约的唯一代码来源，OpenAPI 是生成产物。
- 现有早期 `stream_gateway/schemas/camera.py` 已删除或迁移，无法与新契约并存。
- 真实应用已经注册全部 Cameras MVP 路径，未实现 handler 只包含一行
  `raise NotImplementedError`，没有稳定化临时失败行为。
- 前端可从路径级 OpenAPI 生成完整 operation、请求、成功响应和 Problem 类型。
- 后续功能切片只需在原 Router 上用真实实现替换 `NotImplementedError` 并重新生成产物，无需
  重新定义 DTO 或路径。

## 10. 后续交接

步骤 7 只从 `contracts/openapi.json` 生成 TypeScript 类型，不为占位 handler 的临时失败生成
前端业务分支。后续每个功能切片必须在同一个提交中完成：

1. 用真实 handler 替换自己拥有的占位行为。
2. 重新生成 `contracts/openapi.json`、前端类型和相关 Fixture。
3. 添加运行时契约测试，证明成功、业务错误和副作用符合功能文档。

不得只删除 `NotImplementedError` 而不实现功能文档要求的行为。
