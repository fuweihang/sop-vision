# 2026-09-01｜Camera 列表 API

## 变化

- `GET /api/v1/cameras` 从占位路由变为可用业务 API，支持名称/IPv4 搜索和稳定分页。
- 当前页全部 Source 使用一次 MediaMTX Runtime Path 快照生成 Camera 状态、在线计数和默认 Source
  摘要；空页不访问 MediaMTX。
- OpenAPI 增加列表聚合损坏的 `500` 响应，并同步 Frontend 生成类型、Fixture 和 MSW 场景。
- 新增 `camera.list_aggregate_invalid` 脱敏日志事件。

## 影响

- 成功响应为 `200 CameraPage`，只包含非敏感摘要，不设置 `Cache-Control: no-store`。
- 当前页任一持久化聚合损坏时返回 `500 CAMERA_AGGREGATE_INVALID`，不返回部分列表，也不公开
  Camera ID 或损坏字段。
- 数据库不可用返回 `503 DATABASE_UNAVAILABLE`；MediaMTX 故障降级为 `200` 和确定的离线状态。
- 数据库结构、Stream Gateway 协议和配置项没有变化。
- 本次不包含列表页面或 Camera Card 播放，它们仍由后续任务实现。

## 验证

使用 Backend Application/API/PostgreSQL 测试、日志与 OpenAPI 契约测试、Frontend Fixture/MSW 测试、
敏感数据检查，以及 Backend/Frontend 格式、静态检查和构建验证。

当前规则见 [Camera 列表 API](../modules/cameras/camera-list.md)。
