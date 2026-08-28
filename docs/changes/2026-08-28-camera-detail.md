# 2026-08-28｜Camera 只读详情

## 变化

- `GET /api/v1/cameras/{camera_id}` 从占位路由变为可用业务 API，返回完整配置和同批媒体状态。
- Frontend `/cameras/$cameraId` 新增可直接访问和后台刷新的只读详情页，以及专用 404 状态。
- 页面按详情原型的区域顺序展示默认 Source、连接信息、视频源表格和删除区；视觉使用现有 shadcn
  组件与 Design System。
- Camera 状态只在连接信息标题右侧展示，视频源状态使用 Badge；预览区只保留左下角 Source 名称。
- 密码默认以固定星号隐藏，可通过眼睛按钮显隐；RTSP URL 只显示普通文本。

## 影响

- 成功响应是 `200 CameraDetail` 并带 `Cache-Control: no-store`。
- Camera 不存在返回 `404 CAMERA_NOT_FOUND`；聚合损坏返回脱敏的
  `500 CAMERA_AGGREGATE_INVALID`；数据库不可用返回 `503 DATABASE_UNAVAILABLE`。
- MediaMTX 故障降级为 `200` 和确定的离线状态，不阻止用户查看 PostgreSQL 中的配置。
- 详情只保存在浏览器当前会话的内存 Query cache；不创建播放器，不调用 Playback，也没有复制操作。
- 开始预览、编辑、默认源切换和删除只显示禁用的占位控件，不会发起业务请求。
- 数据库结构和配置项无变化。

## 验证

使用 Backend 详情 Application/API/PostgreSQL 测试、Frontend Query/路由/页面测试、契约与敏感数据
检查验证，并通过 Playwright 对照 `docs/prototype/v1.0.html` 检查桌面、窄屏和深色页面。

当前规则见 [Camera 详情](../modules/cameras/camera-detail.md)。
