# 07｜CameraSource WHEP 播放准备与恢复

> 前置：[Stream Gateway](../../../modules/cameras/stream-gateway.md)、
> [媒体对账](../../../modules/cameras/media-reconciliation.md)、
> [Camera 详情](../../../modules/cameras/camera-detail.md)
>
> 交付：`POST /api/v1/camera-sources/{source_id}/playback`
> （`prepareCameraSourcePlayback`）和可复用 WHEP 播放器

## 接口职责

列表和详情中的非空 `whep_url` 是正常播放入口，Frontend 直接使用它连接 MediaMTX。Playback
接口不是每次播放前必经的 URL 查询，而是具有幂等副作用的准备/恢复命令：Path 丢失、配置漂移
或一次 WHEP 协商失败时，它使用 PostgreSQL 最新 Desired State 收敛 MediaMTX。

目标成功响应：

```json
{
  "source_id": "8f14e45f-ea9d-4a7d-9b6d-8c9f0a1b2c3d",
  "protocol": "WHEP",
  "url": "https://vision.example.internal/media/8f14e45f-ea9d-4a7d-9b6d-8c9f0a1b2c3d/whep",
  "status": "AVAILABLE",
  "expires_at": null
}
```

MVP 地址不签名，因此 `expires_at=null`；客户端仍只能使用 API 返回的地址。响应使用
`Cache-Control: no-store`，且不进入浏览器持久化缓存。

| 场景                  | 响应                                           |
| --------------------- | ---------------------------------------------- |
| Source 不存在         | `404 SOURCE_NOT_FOUND`                         |
| Path 已接受但尚未就绪 | `409 PLAYBACK_NOT_AVAILABLE`，`Retry-After: 2` |
| MediaMTX 超时或不可用 | `503 MEDIA_SERVICE_UNAVAILABLE`                |
| MediaMTX 响应无效     | `502 MEDIA_SERVICE_INVALID_RESPONSE`           |

Router、OpenAPI、Frontend Client 和 MSW 已统一冻结为 `POST prepareCameraSourcePlayback`；当前
handler 仍是 Foundation 占位，只有完成本切片的 Backend 行为和测试后才能作为可用恢复接口。

## Backend 行为

1. 通过专用 `get_by_source_id(source_id)` 只读端口加载 Source 及所属完整 Camera；不能扫描全部
   Camera，也不能让 MediaMTX 反向成为配置事实源。
2. 使用数据库最新连接字段构造 Desired Source；Source 已删除时在任何远端写入前返回 `404`。
3. 幂等调用 `ensure_path`。重复 POST 只收敛同一个 Path，不创建数据库 Session 或播放记录。
4. Application Service 拥有 `3s` 总预算，覆盖 `ensure_path` 和后续运行态检查；Adapter 不自动
   重试。严格在线返回 `200 PlaybackInfo`，未就绪返回可重试 `409`。
5. 响应、Problem、结构化日志和追踪不包含凭据、后缀、完整 RTSP URL 或 MediaMTX 原始错误体。

同一 Source 的进程内并发请求应 single-flight 以减少重复重载，但不能依赖进程锁保证跨实例正确；
跨实例重复 replace 必须保持相同 Desired State，后台对账最终处理与更新/删除交错产生的漂移。

## Frontend 播放与恢复

- 07 在 06 已有的只读预览区域内接入播放器；06 不创建播放器、Playback 请求或恢复控件。
- 列表或详情拿到非空 `whep_url` 时直接创建静音、内联播放器，不调用 Playback。
- `whep_url=null && error=MTX_PATH_NOT_FOUND` 时，可见 Card 对同一 Source 自动调用一次 Playback；
  这是 MTX 内存丢失的按需自愈，不是常规 N+1 流程。
- `MTX_PATH_NOT_AVAILABLE` 或 `MTX_PATH_OFFLINE` 不自动循环准备；详情允许用户显式重试。
- `MTX_CONTROL_API_UNAVAILABLE` 等待后台 Query 刷新，不批量触发 Playback。
- 已有 URL 的 WHEP 协商失败时，先关闭 PeerConnection 和轨道，再调用一次 Playback 并仅重试
  一次 WHEP；仍失败交给用户处理。
- 同一 Source 具有 single-flight 和冷却时间；离开视口、切页、页面隐藏或卸载立即关闭浏览器
  资源，但不删除 MediaMTX Path。
- `409` 按 `Retry-After` 最多自动重试 3 次；`503` 不高频重试。

PlaybackInfo 只允许内存缓存。连接字段变化或 Source 删除后移除；恢复响应可临时覆盖本地旧 URL，
但后续列表/详情刷新仍是状态投影事实源。

## 验收

- 正常在线列表 Card 直接使用 `whep_url`，没有逐 Card Playback 请求。
- MTX 重启造成 Path 缺失时，Playback 能恢复单 Source；未访问 Source 仍由后台对账恢复。
- 覆盖已就绪、延迟就绪、持续离线、Source 不存在、超时、503、无效响应和并发重复请求。
- 播放器 Fake 断言 PeerConnection 关闭、轨道停止、`srcObject` 清空和单次恢复重试。
- WHEP 地址、日志、Problem 和缓存无 RTSP 凭据；停止预览不调用配置写 API。
