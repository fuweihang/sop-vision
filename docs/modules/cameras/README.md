# Cameras 模块

Cameras 模块维护 Camera 与 CameraSource 配置，并把 PostgreSQL 中的配置投影到 MediaMTX。当前已经
支持创建、搜索分页列表、查看与完整编辑 Camera、切换默认预览源、MediaMTX Path 读写、运行态
投影、后台媒体恢复，以及可临时切源的详情 WHEP 播放。`/cameras` 已支持 URL 搜索分页和默认
Source 实时预览；Camera 删除仍在 [Cameras MVP 剩余计划](../../plans/cameras-mvp/README.md)中。

## 当前能力

| 能力                                     | 状态   | 详细说明                                      |
| ---------------------------------------- | ------ | --------------------------------------------- |
| Camera 领域、持久化、HTTP 与跨端基础     | 已实现 | [基础能力](foundation.md)                     |
| MediaMTX v1.20.1 协议和部署边界          | 已实现 | [MediaMTX 契约](mediamtx-contract.md)         |
| Path 读写、快照、Source 状态和 WHEP URL  | 已实现 | [Stream Gateway](stream-gateway.md)           |
| PostgreSQL 到 MediaMTX 的周期恢复        | 已实现 | [媒体对账](media-reconciliation.md)           |
| 创建 Camera 及前端新增 Dialog            | 已实现 | [Camera 创建](camera-create.md)               |
| Camera 完整详情 API 与前端详情页         | 已实现 | [Camera 详情](camera-detail.md)               |
| 共享 WHEP Session、临时切源与详情播放器  | 已实现 | [WHEP 浏览器播放](whep-player.md)             |
| Camera 搜索分页列表 API、页面与实时 Card | 已实现 | [Camera 列表](camera-list.md)                 |
| Camera 完整更新与默认源切换              | 已实现 | [Camera 更新与默认预览源](camera-update.md)   |
| Camera 删除                              | 未实现 | [剩余计划](../../plans/cameras-mvp/README.md) |

当前除 `DELETE /api/v1/cameras/{camera_id}` 外，OpenAPI 中的 Cameras handler 均已接入真实
Application Service 和生产依赖。Camera 删除路由仍是唯一占位 handler。

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

- Camera 删除。
- Detection Canvas 和 WebRTC 质量统计。
- 鉴权、RBAC、多租户、录像、截图、回放和 WebSocket 状态推送。
- 软删除以及事务级 Outbox/Saga 媒体投递。

## 公共验证入口

日常交付只在仓库根目录运行统一入口。脚本会根据 `test-impact.json` 中的路径、模块和变更规模选择
需要的 Backend、Frontend、API Contract、敏感数据与 MediaMTX 检查，并把完整日志写入临时目录。

```bash
./scripts/verify-changed.sh
```

只有定位统一入口报告的失败时，才直接运行日志中给出的 Pytest 或 Vitest 命令。
`scripts/check-cameras-contracts.sh`、`scripts/check-cameras-sensitive-data.sh`、
`backend/scripts/check_camera_placeholders.py` 和 `pnpm vendor:check` 保留为专项排障入口；日常交付由
统一入口按实际影响调用。真实 MediaMTX、媒体对账和浏览器播放的额外环境验收见对应主题文档。

PostgreSQL 集成测试必须配置独立的 `TEST_DATABASE_URL`；相关测试被跳过时不能算作完整持久化验收。
`foundation` 门禁允许尚未实现的 handler 保持纯占位，完整 MVP 发布改用 `mvp` 门禁并要求零占位，
详见 [发布门禁计划](../../plans/cameras-mvp/11-release-gates/README.md)。
