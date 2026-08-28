# 06｜Camera 详情

> 前置：[Cameras 基础能力](../../../modules/cameras/foundation.md)、
> [Camera 创建](../../../modules/cameras/camera-create.md)、
> [Stream Gateway](../../../modules/cameras/stream-gateway.md)
>
> 最终交付：`GET /api/v1/cameras/{camera_id}`（`getCamera`）和只读详情路由

## 执行顺序

| 顺序 | 子任务                                                     | 独立交付                         |
| ---- | ---------------------------------------------------------- | -------------------------------- |
| 06.1 | [Backend Camera 详情接口](01-backend-camera-detail-api.md) | 可独立调用和验证的详情 GET 接口  |
| 06.2 | [Frontend 只读详情页](02-frontend-camera-detail-page.md)   | 可直接访问的只读页面和交付文档   |

必须按顺序执行。06.2 开始前先核对 06.1 的实际代码、测试和 OpenAPI 生成物，不能只依据计划假定
Backend 已完成。

## 共同边界

- 06 只实现详情读取和展示；播放器在 07 接入，编辑与默认源切换在 09 接入，删除在 10 接入。
- 不创建、覆盖或删除 MediaMTX Path，不调用 Playback，不增加媒体补偿或通用读取框架。
- RTSP URL 只作为非链接普通文本展示，不提供复制按钮、菜单、提示或 Clipboard API 调用。
- 不显示可操作的启动预览、编辑、默认源切换或删除按钮。
- `CameraDetail` 继续使用现有 Schema、OpenAPI 和生成类型，不另建详情 DTO。

## 06 完成条件

两个子任务全部完成并通过最终验证后，用户可以直接打开 `/cameras/{camera_id}`，查看 Camera 完整
配置、默认 Source 和当前媒体状态，并返回 Cameras 列表。

完成 06 时统一执行文档处理：

1. 新增 `docs/modules/cameras/camera-detail.md`，记录已经实现的接口、页面、错误和排障信息。
2. 更新 `docs/modules/cameras/README.md` 及受影响的当前能力说明。
3. 在 `docs/changes/` 新增交付记录。
4. 把 07 对本计划的链接改为当前能力文档。
5. 从 Cameras MVP 总计划移除 06，但保留本目录，等待用户在后续流程中自行清理；不得提前移除
   07、09 或 10。
