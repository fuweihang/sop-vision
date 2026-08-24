# 01｜Cameras 基础契约

> 阶段：Cameras MVP 公共前置  
> 交付：领域模型、数据库迁移、HTTP 公共机制、前端 API Client、Mock 和契约测试

> 实施拆分：见 [Foundation 顺序执行计划](./execution-plan/README.md)。该计划把本基线拆成可单独指派、提交和验收的步骤；本文件仍是需求与验收事实源。

## 1. 完成目标

建立 Cameras 所需的最小数据和 HTTP 基础，使后续功能切片只定义自己的业务行为，不重复设计 ID、错误和分页。

本模块完成时不要求存在可操作页面，但数据库迁移、公共 Schema、API Client 和 Mock Server 必须能够独立测试。

## 2. 范围

### 后端

- 建立 `cameras` 和 `camera_sources` 表及仓储接口。
- 定义全局唯一、服务端生成的 UUID v4 `camera_id/source_id`。
- 实现统一 Problem Details、字段错误、分页参数和搜索规范化。
- 导出 OpenAPI，并把框架默认字段错误转换为统一 Problem 模型。

### 前端

- 提供类型化 API Client、Problem Details 解析和字段错误映射。
- 提供 Cameras Query Key 工厂。
- 提供首次加载、后台刷新、空数据、搜索无结果和错误状态基元。
- 使用 OpenAPI 生成类型，或用契约测试校验唯一的手写类型来源。

### 不属于本模块

- Camera 业务路由及页面。
- MediaMTX Path 状态映射和 WHEP 播放。
- 通用登录、权限、WebSocket 或全平台基础设施。

## 3. 领域模型

### 3.1 Camera

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `camera_id` | UUID | 服务端生成 UUID v4；主键，全局唯一且创建后不可改变 |
| `name` | string | trim 后 `1-128` 字符 |
| `ip_address` | string | 合法 IPv4 文本 |
| `rtsp_port` | integer | `1-65535`，创建默认 `554` |
| `username` | string | `1-128` 字符 |
| `password` | string | `1-512` 字符 |
| `default_preview_source_id` | UUID | 必须属于当前 Camera |
| `created_at` | datetime | 服务端生成 RFC 3339 UTC |
| `updated_at` | datetime | 服务端生成 RFC 3339 UTC |

MVP 不为名称或 IP 建立唯一索引。

### 3.2 CameraSource

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `source_id` | UUID | 服务端生成 UUID v4；主键，全局唯一且创建后不可改变 |
| `camera_id` | UUID | 所属聚合的逻辑引用；删除 Camera 时由 Repository 在同一事务显式删除 |
| `name` | string | trim 后 `1-128` 字符 |
| `url_suffix` | string | 规范化后 `1-1024` 字符 |
| `sort_order` | integer | 从 `0` 开始，同 Camera 内连续排序 |
| `created_at` | datetime | 服务端生成 RFC 3339 UTC |
| `updated_at` | datetime | 服务端生成 RFC 3339 UTC |

同一 Camera 内对 `(camera_id, url_suffix)` 建立唯一约束。`url_suffix` 比较区分大小写。

PostgreSQL 中上述 ID 字段使用原生 `uuid` 类型，不使用字符串列。UUID 规则：

- 使用符合 RFC 9562 的 UUID v4。
- 由服务端生成；Frontend 不生成正式业务 ID。
- API 使用小写、带连字符的标准形式，例如 `8f14e45f-ea9d-4a7d-9b6d-8c9f0a1b2c3d`。
- 不接受无连字符、花括号包裹、大写或其他非标准文本形式。
- 无效 UUID 路径或字段返回 `422 VALIDATION_ERROR`，字段 code 为 `INVALID_UUID`。

### 3.3 聚合约束

- Camera 必须至少包含一路 Source。
- `default_preview_source_id` 必须指向同一 Camera 下的一路 Source。
- Camera 与 Source 的创建、完整更新和删除使用同一数据库事务。
- Source 顺序由请求数组顺序决定，服务端持久化为连续 `sort_order`。
- 已有 Source 更新时保留 `source_id/created_at`；新增 Source 生成新 ID。
- Source 连接状态和播放地址不写入上述配置表。

## 4. URL 与敏感数据规则

完整 RTSP URL 的生成规则为：

```text
rtsp://{username}:{password}@{ip_address}:{rtsp_port}/{url_suffix}
```

`url_suffix` 规范化步骤：

1. 去除首尾空白。
2. 去除开头的全部 `/`。
3. 规范化后为空则校验失败。
4. 不改变内部字符、大小写、查询字符串或尾部 `/`。

密码按当前 MVP 产品语义保存并在 Camera 详情中回填。必须执行以下保护：

- Camera 详情响应包含 `Cache-Control: no-store`。
- 应用日志、访问日志、异常追踪和指标标签不得记录密码。
- 不得记录完整带凭据 RTSP URL。
- Problem Details 的 `detail/context/errors` 不得回显密码或完整 RTSP URL。
- 列表响应和播放信息响应不得包含用户名、密码或 RTSP URL。

## 5. 通用 HTTP 契约

- REST 前缀为 `/api/v1`。
- 成功请求和响应使用 `application/json`；错误使用 `application/problem+json`。
- JSON 字段使用 `snake_case`，枚举使用大写英文字符串。
- 时间使用 RFC 3339 UTC。
- OpenAPI 将 `camera_id/source_id/default_preview_source_id` 声明为 `type: string, format: uuid`。
- UUID 只用于相等比较和路由，不允许客户端从中推导创建时间或业务含义。
- 每个路由必须有稳定且唯一的 `operation_id`。

## 6. 分页、搜索和固定顺序

Camera 列表统一支持：

| 参数 | 类型 | 默认 | 规则 |
| --- | --- | --- | --- |
| `page` | integer | `1` | `>= 1` |
| `page_size` | integer | `20` | `1-100` |
| `q` | string | 无 | trim，最长 100；空字符串等同未提供 |

分页响应结构：

```json
{
  "items": [],
  "page": 1,
  "page_size": 20,
  "total": 0
}
```

Camera 列表固定按 `created_at ASC, camera_id ASC` 返回，即先创建的 Camera 在前，相同创建
时间使用 `camera_id` 升序保证稳定分页。API 不声明排序参数；额外查询参数（包括旧的
`sort`）被忽略，不报错也不改变固定顺序。非法页码和非法 page size 返回
`422 VALIDATION_ERROR`，并指向对应查询字段。

## 7. 错误模型

```json
{
  "type": "https://sop-vision.local/problems/validation-error",
  "title": "请求字段验证失败",
  "status": 422,
  "code": "VALIDATION_ERROR",
  "detail": "存在一个或者多个无效字段。",
  "instance": "/api/v1/cameras",
  "trace_id": "tr_01J...",
  "errors": [
    {
      "field": "sources[0].url_suffix",
      "code": "REQUIRED",
      "detail": "请输入视频源 URL 后缀。"
    }
  ],
  "context": {}
}
```

稳定字段为 `status/code/errors[].field/errors[].code/context`。前端不得依赖 `title/detail` 编写业务分支。

| HTTP | 使用场景 |
| --- | --- |
| `400` | JSON 可解析但请求整体语义无效 |
| `404` | Camera 或 CameraSource 不存在 |
| `409` | 播放尚不可用 |
| `422` | 请求体或查询字段校验失败 |
| `502` | MediaMTX 返回无效响应 |
| `503` | PostgreSQL 或 MediaMTX 等当前请求必需的依赖暂不可用 |

所有响应包含或透传 `trace_id`；日志使用同一标识关联请求。

## 8. OpenAPI 与前端基础

- OpenAPI 标签仅使用 `cameras` 和 `camera-sources`。
- 请求、成功响应及所有已声明错误都使用显式 Schema。
- Pydantic 请求模型包含与各功能文档一致的 Example。
- 前端 Query Key 工厂只暴露：`cameras({q, page, page_size})`、`camera(cameraId)`、
  `playback(sourceId)`。
- Problem 解析器必须将 `sources[1].name` 等嵌套路径映射到动态表单行。
- Mock Server 至少支持成功、字段错误、404、409、502 和 503。
- CI 比较 OpenAPI 与前端类型，检测字段删除、类型变化和枚举破坏性变更。

## 9. 依赖与 Fixture

本模块只依赖 PostgreSQL 或可执行相同约束的测试数据库。必须提供：

- 空数据库迁移测试。
- 从上一迁移版本升级测试。
- Camera/Source 仓储 Fixture Builder。
- 固定时钟和固定 ID 生成器。
- 前端 Mock Server 场景切换入口。

## 10. 独立验收

1. 空数据库可完成迁移和回滚，DDL 不包含外键且主键、唯一和 CHECK 约束生效。
2. 连续生成的 Camera/Source ID 均为合法 UUID v4，数据库主键拒绝重复 UUID。
3. Camera 删除时所属 Source 由 Repository 在同一数据库事务显式删除，失败时完整回滚。
4. 同一 Camera 内重复规范化后缀被数据库和领域层共同阻止。
5. 嵌套字段错误能映射到准确前端表单项。
6. OpenAPI 类型生成和契约检查可在 CI 中运行。
7. 日志与错误体不包含测试密码或完整 RTSP URL。

## 11. Definition of Done

- 数据库迁移、领域模型、仓储接口和公共 HTTP 组件已实现并测试。
- 前端 API Client、Query Key、Problem 解析和 Mock Server 可供后续切片使用。
- 所有公共 Schema 有固定示例和契约测试。
- 实现说明记录迁移、类型生成、Mock 启动和测试命令。
