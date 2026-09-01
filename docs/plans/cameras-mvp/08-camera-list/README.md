# 08｜Camera 列表与 Cards 预览

> 前置：[Camera 创建](../../../modules/cameras/camera-create.md)、
> [Stream Gateway](../../../modules/cameras/stream-gateway.md)、
> [WHEP 浏览器播放](../../../modules/cameras/whep-player.md)
>
> 最终交付：`GET /api/v1/cameras`（`listCameras`）、可搜索分页的 `/cameras` 页面和可见 Card 的
> 共享 WHEP 预览

08 同时涉及 Backend 列表读取、Frontend 路由与查询状态，以及浏览器媒体生命周期。为保证每个阶段
都能单独实现和验证，按以下顺序执行：

| #   | 任务                                                 | 交付                                             |
| --- | ---------------------------------------------------- | ------------------------------------------------ |
| 01  | [Camera 列表 API](01-camera-list-api/README.md)      | 搜索分页、批量状态投影和稳定 HTTP 契约           |
| 02  | [Camera 列表页面](02-camera-list-page/README.md)     | URL 查询状态、页面状态、分页和不含媒体的静态卡片 |
| 03  | [Camera Card 预览](03-camera-card-preview/README.md) | 视口感知、页面可见性和共享 WHEP Session 生命周期 |

三个任务必须顺序执行。后续任务应以已落地代码、OpenAPI、生成类型和测试为准，不能复制前一任务的临时
实现或绕过其公共接口。

## 共同范围

完成 08 后，用户可以按名称或 IPv4 搜索、分页浏览 Camera、进入详情，并在可见 Card 中查看 Backend
默认 Source 的实时预览。列表配置读取不依赖 MediaMTX 成功，媒体故障只产生确定的离线投影。

列表响应固定为 `{items, page, page_size, total}`，每个 `CameraSummary` 只包含：

- `camera_id/name/ip_address/rtsp_port`
- `status/online_source_count/source_count`
- `default_preview_source.source_id/name/status/last_checked_at/whep_url`
- `created_at/updated_at`

列表、Frontend 日志和错误不得包含 `username/password/url_suffix/rtsp_url`。Card 只使用列表返回的
默认 Source，不读取敏感详情，也不自行拼接媒体 URL。

## 共同不做事项

- 不实现 Camera 更新、切换默认源或删除；这些能力分别由后续 09、10 负责。
- 不添加鉴权、RBAC、多租户、Detection 数据、Canvas、WebRTC Stats、录像、截图或回放。
- 不复制 WHEP reader、Stream Session 或 video 生命周期代码。
- 不增加列表排序选项、额外筛选条件、持久化 Query cache、批量操作或无限滚动。
- 不执行 11 的真实设备、跨网络、容量和长时间连接发布门禁。

## 08 完成条件

只有 01–03 全部完成后，才把 08 视为完成。届时应更新 `docs/modules/cameras/` 的当前能力和排障说明，
在 `docs/changes/` 记录最终用户可见行为，并按上级计划要求从
[Cameras MVP 剩余计划](../README.md)移除 08。阶段性文档处理以各子任务说明为准。
