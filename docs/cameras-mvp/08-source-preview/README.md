# 08｜CameraSource WHEP 预览

> 前置：[Foundation](../01-foundation/README.md)、[详情](../04-camera-detail/README.md)
>
> 交付：`GET /api/v1/camera-sources/{source_id}/playback`
> （`getCameraSourcePlayback`）、MediaMTX Adapter 和 WHEP 播放器

## Playback 契约

成功返回：

```json
{
  "source_id": "8f14e45f-ea9d-4a7d-9b6d-8c9f0a1b2c3d",
  "protocol": "WHEP",
  "url": "https://vision.example.internal/media/8f14e45f-ea9d-4a7d-9b6d-8c9f0a1b2c3d/whep",
  "status": "AVAILABLE",
  "expires_at": null
}
```

MVP 地址不签名，因此 `expires_at=null`；客户端仍必须使用响应 URL，不能自行拼接。

| 场景                     | 响应                                                |
| ------------------------ | --------------------------------------------------- |
| Source 不存在            | `404 SOURCE_NOT_FOUND`                              |
| 映射已接受但 Path 未就绪 | `409 PLAYBACK_NOT_AVAILABLE`，建议 `Retry-After: 2` |
| MediaMTX 超时或不可用    | `503 MEDIA_SERVICE_UNAVAILABLE`                     |
| MediaMTX 响应无效        | `502 MEDIA_SERVICE_INVALID_RESPONSE`                |

## Adapter 与后端

- Path 名称复用[状态契约](../07-source-status/README.md)的 `source_id` 规则。
- `ensure_playback(source_id, config_fingerprint)` 用当前 Camera 配置生成上游 RTSP 地址；指纹变化
  时覆盖或重建同名映射。
- Source 离线时仍可尝试准备；仅 Path 严格在线后返回 AVAILABLE。
- 准备映射总超时 `3s`；响应不得包含凭据、后缀或上游 RTSP URL。
- `peek_playback(source_ids)` 只读在线映射，不因列表/详情查询创建 Path。
- 配置提交后，更新/删除切片调用 `release_source`；释放失败只记录脱敏指标/日志，不回滚。
- Frontend 不访问 Control API，FastAPI 不代理 WHEP 媒体字节；播放失败不阻止配置操作。
- 面向浏览器的 WHEP 服务使用 HTTPS，并由部署层限制允许来源。

## 播放器生命周期

列表卡片进入视口后为默认 Source 请求 Playback；AVAILABLE 后创建静音、内联播放器，浏览器
禁止自动播放时显示按钮。离开视口、切页、搜索变化或卸载时关闭 PeerConnection 和轨道；
同一卡片不能并行创建多个会话。`409` 按 Retry-After 最多自动重试 3 次，`503` 不高频重试。

详情页初始不自动播放。用户点击开始后请求 Playback，可取消；点击停止、离开页面、切换默认
源或页面隐藏时立即关闭 PeerConnection、停止轨道并清空 `<video>.srcObject`。恢复可见后需
用户再次开始；失败重试前必须释放旧会话。停止预览不得调用配置写 API。

PlaybackInfo 只使用内存 Query cache。连接字段/后缀变化后失效，Source/Camera 删除后移除；
默认源切换保留旧 Source 缓存但组件改用新 ID。地址失效时清除并重新获取一次，仍失败则交给
用户重试。

## 验收

- Gateway Stub 覆盖立即/延迟/持续不可用、超时、503、无效响应、指纹重建和释放结果。
- 播放器 Fake 断言创建次数、PeerConnection 关闭、轨道停止和 srcObject 清理。
- 列表可见性、详情启停、隐藏、切源和卸载均无会话泄漏。
- WHEP 地址和日志无 RTSP 凭据；MediaMTX 停机不影响 Camera 配置读写。
