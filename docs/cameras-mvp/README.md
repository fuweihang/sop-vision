# Cameras MVP：开发文档索引

> 文档状态：实施基线  
> REST API 前缀：`/api/v1`  
> 更新日期：2026-08-24

本目录是 Cameras 第一阶段 MVP 的前后端契约、开发边界和验收事实源。每份功能文档都能形成一个可单独指派、实现和验收的交付单元；除本目录内明确列出的依赖外，不依赖其他业务模块。

## 1. MVP 目标

用户可以完成以下闭环：

1. 录入一台物理摄像头及其多路 RTSP 视频源。
2. 查看、搜索和分页浏览 Camera 卡片。
3. 查看 Camera 详情及全部 CameraSource。
4. 编辑 Camera 基础信息及完整 Source 集合。
5. 为 Camera 选择唯一的默认预览源。
6. 查看 Source 连接状态和 Camera 聚合状态。
7. 开始、停止和恢复默认源 WHEP 预览。
8. 删除 Camera 及其所属 CameraSource。

## 2. 范围边界

### 2.1 本阶段包含

- `Camera` 与 `CameraSource` 聚合的数据模型和数据库迁移。
- Camera 创建、列表、详情、完整更新、默认源切换和删除。
- Source 新增、编辑、排序和删除。
- 通过 MediaMTX Control API `/paths/list` 读取 Source 状态并完成 Camera 状态聚合。
- MediaMTX WHEP 播放地址获取及浏览器播放器生命周期。
- Cameras 所需的最小 HTTP 错误、分页、OpenAPI 和前端 API Client。
- 加载、刷新、空数据、搜索无结果、字段错误、播放失败和删除确认交互。

### 2.2 本阶段不包含

- Cameras 之外的业务模块、数据模型和界面。
- 跨业务计数、删除保护或级联处理。
- 通用用户、角色、权限、审计和生产鉴权方案。
- 通用健康检查、WebSocket 消息协议和非 Cameras 页面。
- 历史视频、录像、截图、证据和回放。
- Camera 启用/停用、厂商管理、批量导入导出和连接测试按钮。
- 可靠异步基础设施清理及其运维管理页面。

后续新增业务能力时，应重新分析其对 Cameras 的影响，并以独立变更补充 Cameras 契约；本阶段不预留未被 MVP 使用的字段、错误码或查询端口。

## 3. 领域边界

```text
Camera 1 ─── N CameraSource
Camera.default_preview_source_id ─── 1 CameraSource
```

- `Camera` 是聚合根，Camera 与完整 CameraSource 集合在一个数据库事务内保存。
- Camera 至少包含一路 Source。
- Camera 必须且只能有一路默认预览 Source。
- `camera_id` 和 `source_id` 均由服务端生成，使用标准 UUID v4；整个系统内必须唯一，创建后不可改变。
- 更新时已有 Source 保留 `source_id`；请求中缺失的已有 Source 表示删除。
- Source 的运行状态是短期投影，不属于 PostgreSQL 配置事实。
- 播放会话是浏览器本地状态，不改变 Camera 或 Source 配置。

## 4. 数据流

```text
配置：Browser -> FastAPI -> PostgreSQL
状态：FastAPI -> MediaMTX Control API /paths/list -> FastAPI -> Browser
播放信息：Browser -> FastAPI -> MediaMTX Adapter
视频：Browser -> MediaMTX WHEP
```

- PostgreSQL 是 Camera 和 CameraSource 配置的事实源。
- Source 状态不在 PostgreSQL 或进程内持久化；Camera 列表/详情读取 MediaMTX Path 列表后即时映射。
- FastAPI 不代理视频字节，只返回浏览器可访问的 WHEP 地址。
- Camera 配置读取不因 MediaMTX Control API 故障而失败；此时 Source 按 `OFFLINE` 返回。

## 5. 功能文档与交付顺序

| 顺序 | 文档 | 独立可演示结果 |
| --- | --- | --- |
| 1 | [基础契约](./01-foundation/README.md) | 数据库迁移、公共 Schema、API Client 和契约测试 |
| 2 | [创建 Camera](./02-camera-create/README.md) | 从表单创建包含多路 Source 的 Camera |
| 3 | [Camera 列表](./03-camera-list/README.md) | 搜索、分页并展示 Camera 卡片 |
| 4 | [Camera 详情](./04-camera-detail/README.md) | 通过独立路由查看 Camera 和 Source 信息 |
| 5 | [更新 Camera](./05-camera-update/README.md) | 编辑基础字段和完整 Source 集合 |
| 6 | [切换默认预览源](./06-default-preview-source/README.md) | 从详情页切换默认 Source |
| 7 | [Source 状态](./07-source-status/README.md) | 展示 Source 状态和 Camera 聚合状态 |
| 8 | [Source 预览](./08-source-preview/README.md) | 获取 WHEP 地址并管理播放器生命周期 |
| 9 | [删除 Camera](./09-camera-delete/README.md) | 二次确认后删除 Camera 聚合 |

基础契约是所有功能切片的公共前置。其余切片可通过文档规定的 Fixture、Fake 和 Mock API 并行开发。

## 6. API 总表

以下路径省略公共前缀 `/api/v1`。

| 方法 | 路径 | 所有者 | 成功响应 |
| --- | --- | --- | --- |
| `GET` | `/cameras` | Camera 列表 | `200` 分页摘要 |
| `POST` | `/cameras` | 创建 Camera | `201` Camera 详情 |
| `GET` | `/cameras/{camera_id}` | Camera 详情 | `200` Camera 详情 |
| `PUT` | `/cameras/{camera_id}` | 更新 Camera | `200` Camera 详情 |
| `PATCH` | `/cameras/{camera_id}/default-preview-source` | 默认预览源 | `200` 更新结果 |
| `DELETE` | `/cameras/{camera_id}` | 删除 Camera | `204` |
| `GET` | `/camera-sources/{source_id}/playback` | Source 预览 | `200` PlaybackInfo |

本阶段不增加仅供未来消费者使用的 CameraSource 选择列表接口。Camera 页面所需 Source 信息由 Camera 详情返回。

## 7. 前端路由和缓存

建议路由：

```text
/cameras
/cameras/{camera_id}
```

Query Key：

```text
["cameras", {q, page, page_size}]
["camera", cameraId]
["playback", sourceId]
```

| 变更 | 必须更新或失效的缓存 |
| --- | --- |
| 创建 Camera | `cameras` |
| 更新 Camera | `cameras`、当前 `camera`、受影响的 `playback` |
| 切换默认源 | `cameras`、当前 `camera` |
| 删除 Camera | `cameras`、当前 `camera`、所属 Source 的 `playback` |
| Source 状态变化 | 局部更新 `cameras` 和当前 `camera` 的状态字段 |

页面刷新后必须能从 URL 恢复列表或详情页面。首次加载与后台刷新应采用不同视觉反馈，已有内容不得因后台刷新短暂消失。

## 8. 已冻结的 MVP 决策

1. Camera 名称和 IP 不做唯一约束。
2. IP 地址仅接受 IPv4；RTSP 端口默认 `554`，范围 `1-65535`。
3. 同一 Camera 内规范化后的 `url_suffix` 必须唯一，比较区分大小写。
4. 所有 Cameras 持久化业务 ID 使用服务端生成的 UUID v4；API 使用小写、带连字符的标准 UUID 文本。
5. 保存 Camera 时不主动验证 RTSP 可用性；离线配置仍可保存。
6. Source 状态为 `ONLINE/OFFLINE`；Camera 状态为 `ONLINE/OFFLINE/DEGRADED`。
7. MediaMTX Path `name` 必须直接使用 `source_id` 的标准 UUID 文本，不添加前缀或后缀。
8. Source 对应的 MediaMTX Path `name` 不存在，或 `available/online` 任一项不严格等于 `true` 时，Source 为 `OFFLINE`；仅名称匹配且 `available === true && online === true` 时为 `ONLINE`。
9. Camera 详情按当前产品基线返回用户名、密码和完整 RTSP URL；响应使用 `Cache-Control: no-store`，日志必须脱敏。
10. 创建、更新、切换默认源和删除均使用普通 HTTP 写请求；服务端执行每个通过校验的请求。
11. 删除 Camera 时只校验资源存在性，随后直接删除聚合。
12. 删除提交后仅进行播放映射的尽力释放，不引入可靠异步清理。
13. 页面预览启停只影响浏览器播放器，不改变持久化配置。
14. Camera 列表固定按 `created_at ASC, camera_id ASC` 返回，不提供客户端排序参数；额外
    查询参数（包括旧的 `sort`）被忽略。

## 9. Cameras MVP 总验收

1. 创建包含两路 Source 的 Camera，服务端生成全局唯一的 UUID v4 Camera/Source ID，并规范化 URL 后缀。
2. 列表区分无数据和搜索无结果，可按名称或 IP 搜索，并按创建先后稳定分页。
3. 详情展示基础字段、默认源和完整 Source 集合，敏感响应不进入 HTTP 缓存或日志。
4. 编辑时可保留、增加、修改和删除 Source，已有 Source ID 不改变。
5. 无 Source、重复 Source 后缀、零个或多个默认源均被精确校验。
6. 默认源切换成功并更新列表与详情缓存。
7. `/paths/list` 中 Path 的 `available/online` 组合、Path 缺失及 Control API 不可用时均有确定状态。
8. WHEP 地址正常、未就绪、媒体服务不可用及播放器失败时均有可恢复交互。
9. Camera 删除成功后返回列表；当前预览关闭，基础数据不可再读取。

## 10. 全局 Definition of Done

每个功能切片完成时必须满足：

- API、数据字段、错误码和缓存行为与对应文档一致。
- 后端测试覆盖正常、校验、资源不存在和依赖故障路径。
- 前端覆盖加载、成功、空状态、字段错误和可恢复失败状态。
- 提供不依赖真实摄像头或 MediaMTX 的 Fixture/Fake。
- OpenAPI 与前端类型由同一契约来源生成或校验。
- 日志包含 `trace_id`，且不包含密码或完整带凭据 RTSP URL。
- 对应功能可以独立启动、演示和验收。
- 实现目录 README 记录启动方式、测试命令和已知 MVP 限制。
