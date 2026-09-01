# Cameras 模块

Cameras 模块维护 Camera 与 CameraSource 配置，并把 PostgreSQL 中的配置投影到 MediaMTX。当前已经
支持创建、搜索分页列表和只读查看 Camera、MediaMTX Path 读写、运行态投影、后台媒体恢复，以及可
临时切源的详情 WHEP 播放；列表页面、编辑和删除仍在
[Cameras MVP 剩余计划](../../plans/cameras-mvp/README.md)中。

## 当前能力

| 能力                                    | 状态   | 详细说明                                      |
| --------------------------------------- | ------ | --------------------------------------------- |
| Camera 领域、持久化、HTTP 与跨端基础    | 已实现 | [基础能力](foundation.md)                     |
| MediaMTX v1.20.1 协议和部署边界         | 已实现 | [MediaMTX 契约](mediamtx-contract.md)         |
| Path 读写、快照、Source 状态和 WHEP URL | 已实现 | [Stream Gateway](stream-gateway.md)           |
| PostgreSQL 到 MediaMTX 的周期恢复       | 已实现 | [媒体对账](media-reconciliation.md)           |
| 创建 Camera 及前端新增 Dialog           | 已实现 | [Camera 创建](camera-create.md)               |
| Camera 完整详情 API 与前端只读详情页    | 已实现 | [Camera 详情](camera-detail.md)               |
| 共享 WHEP Session、临时切源与详情播放器 | 已实现 | [WHEP 浏览器播放](whep-player.md)             |
| Camera 搜索分页列表 API                 | 已实现 | [Camera 列表 API](camera-list.md)             |
| 列表页面、Card 播放、更新和删除         | 未实现 | [剩余计划](../../plans/cameras-mvp/README.md) |

“路由已出现在 OpenAPI”只表示占位契约可用于生成跨端类型，不表示 handler 已经可用。当前
`GET /api/v1/cameras`、`POST /api/v1/cameras` 和 `GET /api/v1/cameras/{camera_id}` 是可用的
Camera 业务 handler。

## 模块边界

```text
Frontend → FastAPI Cameras API → Cameras Application → PostgreSQL
                                      │
                                      └→ Stream Gateway Port → MediaMTX
```

- PostgreSQL 是 Camera 和 CameraSource Desired State 的唯一事实源。
- MediaMTX 保存允许丢失并可重建的媒体配置和运行状态。
- Camera 写操作先提交数据库，再尽力同步 MediaMTX；媒体失败不能伪装成数据库回滚。
- `app/modules/cameras` 拥有 Camera 聚合和配置流程；`app/modules/stream_gateway` 只拥有外部媒体协议。
- Frontend 不直接访问 MediaMTX Control API，也不自行拼接 RTSP 或 WHEP 地址。

选择 PostgreSQL 作为配置事实源、把 MediaMTX 作为可重建运行态的原因见
[决策 0001](../../decisions/0001-camera-config-and-media-state.md)。

## 当前不支持

- Camera 列表页面、编辑、切换默认预览源和删除。
- Camera Cards 播放、Detection Canvas 和 WebRTC 质量统计。
- 鉴权、RBAC、多租户、录像、截图、回放和 WebSocket 状态推送。
- 软删除以及事务级 Outbox/Saga 媒体投递。

实现新能力后，先更新本表和对应主题文档，再新增 `docs/changes/` 记录并移除完成的计划。
