# 06｜Camera 详情

> 前置：[Foundation](../01-foundation/README.md)、[创建](../05-camera-create/README.md)、[Stream Gateway Adapter](../03-stream-gateway-adapter/README.md)
>
> 交付：`GET /api/v1/cameras/{camera_id}`（`getCamera`）和详情路由；播放器在 07 接入

## CameraDetail

用户可以通过 `/cameras/{camera_id}` 查看完整配置、默认源和当前媒体投影，并进入后续编辑、
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
`context.camera_id` 为请求 ID。完整安全边界见 [Foundation](../01-foundation/README.md#敏感数据)。

## 读取与投影

- 一次读取 Camera 和按序 Source，验证聚合，再派生供详情展示的完整 RTSP URL。
- Source 始终按持久化顺序；`source_count == sources.length`，且恰好一路默认源。
- 所有 Source 共享一次 `500ms` 完整 Path 快照，不得逐 Source 调用 Control API。
- 状态映射遵循 [Adapter](../03-stream-gateway-adapter/README.md#严格状态映射)。外部故障使用降级值，
  不让配置读取失败。
- 只有严格在线的 Path 返回 `whep_url`；该 URL 表示 `last_checked_at` 时的观察结果，不承诺之后
  建立的浏览器会话一定成功。
- 详情读取只观察 Runtime State，不创建、覆盖或删除 Path。缺失映射由后台对账或 07 Playback
  准备命令恢复。
- 配置聚合损坏返回 `500 CAMERA_AGGREGATE_INVALID` 并告警，不返回部分详情。

## 前端与验收

- 首次进入显示当前 Camera 骨架；后台刷新保留内容；`404` 提供返回 Cameras 操作。
- Source 展示名称、完整 RTSP URL、默认标记、状态和最近检查时间。
- 复制 RTSP URL 是显式操作，按钮必须提示其中包含凭据。
- 本切片先完成配置和投影页面；07 接入播放器后，非空 `whep_url` 直接播放，空值按稳定 error
  决定恢复或提示。
- 查询缓存只在当前会话内短期保存；更新/默认源切换后刷新，删除后移除且不重试。
- 验收覆盖直接 URL 恢复、顺序/默认/计数、RTSP URL 派生、一次快照、外部降级、404、聚合损坏、
  `no-store` 和敏感数据门禁。
