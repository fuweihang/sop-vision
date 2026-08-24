# 01｜Cameras Foundation 契约

> 公共前置；实施状态与步骤见[执行计划](./execution-plan/README.md)。

Foundation 只建立后续切片共享的数据、事务、HTTP、跨端类型和测试基础，不交付可操作的
Camera 页面或业务行为。本文件是公共规则的唯一事实源；功能文档只描述差异。

## 领域与字段

| 字段                        | 规则                                                                        |
| --------------------------- | --------------------------------------------------------------------------- |
| `camera_id/source_id`       | 服务端生成 UUID v4，全局唯一，创建后不变                                    |
| `name`                      | trim 后 `1-128` 字符                                                        |
| `ip_address`                | IPv4                                                                        |
| `rtsp_port`                 | `1-65535`，创建默认 `554`                                                   |
| `username/password`         | 分别 `1-128`、`1-512` 字符，不自动 trim                                     |
| `default_preview_source_id` | 必须属于当前 Camera                                                         |
| `url_suffix`                | trim、移除全部前导 `/`，结果 `1-1024` 字符；其余大小写、查询串和尾 `/` 不变 |
| `sort_order`                | 请求数组顺序，从 `0` 开始连续                                               |
| `created_at/updated_at`     | 服务端 RFC 3339 UTC 时间                                                    |

Camera 至少包含一路 Source，且恰好一路默认。规范化后缀在同一 Camera 内大小写敏感唯一。
已有 Source 更新时保留 `source_id/created_at`；新增项生成新 ID；持久化数据不满足不变量时
抛出聚合损坏错误，不静默修复或返回部分数据。

公共字段错误 code：必填 `REQUIRED`、超长 `STRING_TOO_LONG`、非法 IPv4
`INVALID_IP_ADDRESS`、非法 UUID `INVALID_UUID`、数值越界 `OUT_OF_RANGE`、未知字段
`UNKNOWN_FIELD`。聚合和所有权错误由对应功能切片定义字段位置。

完整 RTSP URL 按以下冻结语义派生，不单独持久化：

```text
rtsp://{username}:{password}@{ip_address}:{rtsp_port}/{url_suffix}
```

## 持久化与事务

PostgreSQL 使用原生 `uuid`、`inet` 和 `timestamptz`。`cameras` 与 `camera_sources` 不建立
外键；数据库负责主键、IPv4、端口、非负顺序，以及同 Camera 后缀/顺序的延迟唯一约束。

跨表不变量由 Camera 专用 Repository/UoW 维护：

- 所有既有聚合写入先锁 Camera，再按 `source_id` 锁全部 Source。
- `add/save/delete` 只 flush；Application Service 显式调用 UoW `commit/rollback`。
- 创建、完整更新和删除在一个事务内完成；删除先显式删除 Source，再删除 Camera。
- 数据库提交后才能更新或释放 MediaMTX 映射；外部失败不能伪装成数据库回滚。
- ORM Row 不进入领域/Application Service；领域对象不依赖 FastAPI、Pydantic 或 SQLAlchemy。
- 引用完整性巡检检测孤儿 Source、缺失/跨 Camera 默认源和无 Source Camera，只告警不修复。

公共持久化端口为 `CameraRepository.add/save/get/list/count/delete` 和
`CameraUnitOfWork.commit/rollback`。列表搜索对名称和 IPv4 做大小写无关的字面包含匹配；
`%/_/\` 不作为 SQL 通配符。结果固定按 `created_at ASC, camera_id ASC` 分页，越界页返回空集。

## HTTP 契约

- API 前缀 `/api/v1`；JSON 字段使用 `snake_case`，枚举使用大写英文值。
- UUID 路径和字段只接受小写、带连字符、RFC variant 正确的 UUID v4 文本。
- 每条路由使用显式、全局唯一的 `operation_id`。
- 成功响应为 `application/json`；结构化错误为 `application/problem+json`。
- 列表参数：`page >= 1`，`1 <= page_size <= 100`，`q` trim 后最长 100，空白等同未提供。
- 额外查询参数被忽略；请求 DTO 的未知字段返回 `422 UNKNOWN_FIELD`。
- 成功和错误响应均携带 `X-Trace-Id`；Problem body 使用同一 `trace_id`。

Problem 采用以下稳定字段；前端业务分支只能依赖 `status/code/errors/context`，不能比较
`title/detail`：

```json
{
  "type": "urn:sop-vision:problem:validation-error",
  "title": "请求字段验证失败",
  "status": 422,
  "code": "VALIDATION_ERROR",
  "detail": "存在一个或者多个无效字段。",
  "instance": "/api/v1/cameras",
  "trace_id": "tr_...",
  "errors": [
    { "field": "sources[0].name", "code": "REQUIRED", "detail": "..." }
  ],
  "context": {}
}
```

| HTTP  | 公共用途                             |
| ----- | ------------------------------------ |
| `400` | 请求整体语义无效                     |
| `404` | Camera 或 Source 不存在              |
| `409` | 播放尚不可用                         |
| `422` | 路径、查询或请求字段错误             |
| `500` | 持久化聚合损坏等服务端不变量错误     |
| `502` | MediaMTX 响应无效                    |
| `503` | 当前请求必需的数据库或媒体依赖不可用 |

框架校验不得公开 Pydantic 原始 input；数据库错误不得公开 SQL、参数或约束名。仅当应用层能
准确定位字段时，数据库后缀冲突才可转换为 `DUPLICATE_SOURCE_SUFFIX`。

## 敏感数据

- CameraDetail 是唯一返回 `username/password/rtsp_url` 的公共形状，成功响应必须
  `Cache-Control: no-store`。
- 列表、PlaybackInfo、Problem、日志、指标、追踪和错误上报不得包含凭据或完整 RTSP URL。
- Secret/ORM/领域对象的默认 `repr/str` 不得输出密码。
- CameraDetail 只在当前浏览器会话内存中短期保存，不进入 localStorage、IndexedDB、离线缓存
  或持久化 Query cache；错误上报不得附带完整响应。

## 前端公共契约

Query Key 只有以下三种：

```text
["cameras", {q, page, page_size}]
["camera", cameraId]
["playback", sourceId]
```

| 变更       | 更新或失效                                                  |
| ---------- | ----------------------------------------------------------- |
| 创建       | `cameras`                                                   |
| 更新       | `cameras`、当前 `camera`、受连接变化或删除影响的 `playback` |
| 切换默认源 | `cameras`、当前 `camera`                                    |
| 删除       | `cameras`、当前 `camera`、所属 Source 的 `playback`         |
| 状态刷新   | 仅合并 `cameras/camera` 的状态字段                          |

首次加载、后台刷新、空数据、搜索无结果和可恢复失败是不同页面状态。后台刷新保留旧内容；
页面 URL 必须恢复列表查询或 Camera 详情。

## Foundation 完成条件

- 迁移、领域聚合、Repository/UoW、HTTP 公共机制均通过单元与 PostgreSQL 集成测试。
- 全部 Cameras Schema 和目标路由注册到真实应用，OpenAPI 可确定性生成。
- 前端类型只从 OpenAPI 生成，Client、Problem 解析、Query Key 和 MSW 基础可独立测试。
- CI 检查迁移、契约漂移、生成产物、敏感数据和占位 handler。
- Foundation 不实现 02–09 的业务 Service 或完成态页面。
