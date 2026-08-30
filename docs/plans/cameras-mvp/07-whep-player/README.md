# 07｜CameraSource WHEP 播放器

> 前置：[Stream Gateway](../../../modules/cameras/stream-gateway.md)、
> [媒体对账](../../../modules/cameras/media-reconciliation.md)、
> [Camera 详情](../../../modules/cameras/camera-detail.md)
>
> 交付：可复用 WHEP 播放器

## 播放入口

列表和详情中的非空 `whep_url` 是正常播放入口，Frontend 直接使用它连接 MediaMTX。

## Frontend 播放

- 07 在 06 已有的只读预览区域内接入播放器；06 不创建播放器。
- 列表或详情拿到非空 `whep_url` 时直接创建静音、内联播放器。
- `whep_url=null` 时不创建播放器。
- 已有 URL 的 WHEP 协商失败时，先关闭 PeerConnection 和轨道，再仅重试一次 WHEP；仍失败交给
  用户处理。
- 同一 Source 具有 single-flight 和冷却时间；离开视口、切页、页面隐藏或卸载立即关闭浏览器
  资源，但不删除 MediaMTX Path。

## 验收

- 正常在线列表 Card 直接使用 `whep_url`。
- 播放器 Fake 断言 PeerConnection 关闭、轨道停止、`srcObject` 清空和单次重试。
- WHEP 地址、日志和缓存无 RTSP 凭据；停止预览不调用配置写 API。
