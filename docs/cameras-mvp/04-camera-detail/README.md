# 04｜Camera 详情

> 前置：[Foundation](../01-foundation/README.md)
>
> 交付：`GET /api/v1/cameras/{camera_id}`（`getCamera`）和详情路由

## 目标与 CameraDetail

用户可以通过 `/cameras/{camera_id}` 查看完整配置、默认源、状态和播放投影，并进入编辑、
默认源切换、预览或删除操作。

`CameraDetail` 是创建、详情和更新成功响应共享的唯一完整形状：

| 层级        | 字段                                                                |
| ----------- | ------------------------------------------------------------------- |
| Camera      | `camera_id/name/ip_address/rtsp_port/username/password`             |
| 聚合        | `default_preview_source_id/status/online_source_count/source_count` |
| Source      | `source_id/name/url_suffix/rtsp_url/is_default_preview`             |
| Source 投影 | `status/last_checked_at/error/whep_url`                             |
| 时间        | `created_at/updated_at`                                             |

成功返回 `200` 和 `Cache-Control: no-store`。不存在返回 `404 CAMERA_NOT_FOUND`，
`context.camera_id` 为请求 ID。完整安全边界见[Foundation](../01-foundation/README.md#敏感数据)。

## 响应与后端行为

- Source 始终按持久化顺序；`source_count == sources.length`。
- 恰好一路 `is_default_preview=true`，其 ID 等于 `default_preview_source_id`。
- `rtsp_url` 每次由当前 Camera 连接字段和 Source 后缀派生。
- 状态、在线数、错误和 WHEP 投影遵循[状态](../07-source-status/README.md)与
  [预览](../08-source-preview/README.md)契约；外部失败使用降级值，不让配置读取失败。
- 配置聚合损坏返回 `500 CAMERA_AGGREGATE_INVALID` 并告警，不返回部分详情。

后端一次读取 Camera 和按序 Source，验证聚合，派生 RTSP URL，共享一次 Path 快照并计算
投影，然后返回详情。状态/播放投影受 `500ms` 总等待上限约束，超时后按确定值降级。

## 前端

- 首次进入显示当前 Camera 的骨架；后台刷新保留内容；`404` 提供返回 Cameras 操作。
- Source 展示名称、完整 RTSP URL、默认标记、状态和最近检查时间。
- 复制 RTSP URL 是显式操作，按钮必须提示其中包含凭据。
- 默认预览区域使用 `whep_url`，为 `null` 时显示未就绪；离开页面释放播放器。
- 查询缓存只在当前会话内短期保存；更新/默认源切换后刷新，删除后移除且不重试。

## 验收

- 直接访问 URL 可恢复页面；Source 顺序、默认源、计数和派生 URL 正确。
- 成功响应 `no-store`；浏览器持久化、日志和监控找不到测试密码。
- 状态或媒体故障仍返回配置 `200`；不存在与聚合损坏使用稳定错误。
- 首次失败、后台刷新失败、404 和投影降级均有明确恢复行为。
