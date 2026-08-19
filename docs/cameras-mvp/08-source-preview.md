# 08｜CameraSource WHEP 预览

> 前置：[Cameras 基础契约](./01-foundation.md)、[Camera 详情](./04-camera-detail.md)  
> 交付：Playback API、MediaMTX Adapter、WHEP 播放器和失败恢复

## 1. 完成目标

用户可以在 Cameras 列表或详情中预览默认 CameraSource。FastAPI 只准备播放映射并返回 WHEP 地址，浏览器视频流直接连接 MediaMTX。

开始和停止预览是浏览器本地会话操作，不修改 Camera 或 CameraSource 配置。

## 2. 范围

### 后端

- 根据稳定 `source_id` 读取 CameraSource 和当前 Camera 连接配置。
- 封装 MediaMTX 映射准备、就绪查询和尽力释放。
- 返回业务化 WHEP URL，不代理视频字节流。
- 映射 MediaMTX 未就绪、不可用和无效响应。

### 前端

- WHEP 播放器适配器和会话资源释放。
- 列表可见性驱动的懒加载预览。
- 详情页显式开始/停止、加载、失败和重试交互。
- 默认 Source 改变时关闭旧会话并加载新 Source。

### 不属于本模块

- Source 连通状态判定。
- 视频录制、截图、回放、转码设置和画面叠加层。
- MediaMTX 通用运维管理页。
- 可靠异步映射清理。

## 3. Playback API

```http
GET /api/v1/camera-sources/8f14e45f-ea9d-4a7d-9b6d-8c9f0a1b2c3d/playback
```

成功：

```json
{
  "source_id": "8f14e45f-ea9d-4a7d-9b6d-8c9f0a1b2c3d",
  "protocol": "WHEP",
  "url": "https://vision.example.internal/media/8f14e45f-ea9d-4a7d-9b6d-8c9f0a1b2c3d/whep",
  "status": "AVAILABLE",
  "expires_at": null
}
```

MVP 地址不带临时签名，因此 `expires_at=null`。客户端仍必须使用响应字段，而不能自行拼接 URL。

错误：

| 场景 | 响应 |
| --- | --- |
| Source 不存在 | `404 SOURCE_NOT_FOUND` |
| 映射已接受但 Path 尚不可播放 | `409 PLAYBACK_NOT_AVAILABLE` |
| MediaMTX 暂不可用或超时 | `503 MEDIA_SERVICE_UNAVAILABLE` |
| MediaMTX 返回无法解析的响应 | `502 MEDIA_SERVICE_INVALID_RESPONSE` |

Source 状态为 `OFFLINE` 时后端仍可尝试准备映射；只有对应 Path 的 `available === true && online === true` 时才返回可播放地址。

## 4. 映射规则

- MediaMTX 业务 Path 的 `name` 直接等于 `source_id` 的标准 UUID 文本，不添加前缀或后缀；Frontend 不得自行拼接 MediaMTX URL。
- Adapter 使用 Camera 当前连接字段生成 RTSP 上游地址，完整地址不出现在 Adapter 日志。
- `ensure_playback(source_id, config_fingerprint)` 根据当前 Source 配置准备播放映射。
- 配置指纹变化时，Adapter 使用新上游配置覆盖或重建同名映射。
- Source 删除后由更新或删除模块调用 `release_source(source_id)`。
- MVP 的释放是提交后的尽力操作；失败只记录指标和脱敏日志，不回滚 Camera 配置事务。

内部只读投影 `peek_playback(source_ids[])` 只为 `available === true && online === true` 的 Path 返回地址，不因列表/详情读取主动创建映射。其他情况返回 `whep_url=null`。

## 5. 后端处理流程

1. 按 `source_id` 读取 Source 和所属 Camera；不存在返回 `404`。
2. 生成当前配置指纹和 RTSP 上游地址。
3. 调用 MediaMTX Adapter 准备映射，总超时为 3 秒。
4. Adapter 确认 Path 的 `available/online` 均为 `true` 时返回 PlaybackInfo。
5. Adapter 接受配置但 Path 尚不可播放时返回 `409`，建议 `Retry-After: 2`。
6. 下游不可用、超时或响应无效时返回稳定 Problem。

Playback API 响应不得包含 Camera 用户名、密码、URL 后缀或 RTSP URL。

## 6. 列表预览行为

- Camera 卡片进入可见区域后，预览组件为默认 `source_id` 调用 Playback API。
- 获得 `AVAILABLE` 地址后创建静音、内联的 WHEP 播放器；浏览器禁止自动播放时显示播放按钮。
- 卡片离开可见区域、切页、搜索结果变化或组件卸载时关闭 PeerConnection 和媒体轨道。
- 同一张卡片不得并行创建多个会话。
- `409` 根据 `Retry-After` 最多自动重试 3 次；随后显示“预览不可用”和手动重试。
- `503` 不进行高频重试，展示媒体服务暂不可用。

## 7. 详情预览行为

- 详情页初始显示默认 Source 和“开始预览”操作，不自动占用播放会话。
- 点击开始后请求 Playback API，并在加载期间允许取消。
- 点击停止、离开页面或切换默认 Source 时立即关闭 PeerConnection、停止媒体轨道并清空 `<video>.srcObject`。
- 停止预览不调用业务配置变更 API。
- 首次连接失败允许手动重试；重试前必须释放失败会话。
- 页面进入后台时暂停或停止策略固定为停止；重新可见后由用户再次开始。

## 8. 前端缓存与地址刷新

Query Key：

```text
["playback", sourceId]
```

- PlaybackInfo 只保存在内存，不持久化。
- Camera 连接信息或 Source 后缀更新后失效相关 `playback`。
- Source 删除和 Camera 删除后移除相关 `playback`。
- 默认源切换不删除旧 Source 缓存，但当前组件必须改用新 Source ID。
- WHEP 请求返回地址失效错误时，清除缓存并重新获取一次 PlaybackInfo；仍失败则交给用户重试。

## 9. 安全与基础设施约束

- Frontend 不访问 MediaMTX Control API。
- FastAPI 不代理 WHEP 媒体字节流。
- 对浏览器返回的 WHEP URL 不包含 RTSP 凭据。
- MediaMTX Adapter 日志不得记录完整上游 URL、请求体中的密码或下游敏感响应。
- WHEP 服务应与前端使用 HTTPS，并由部署层配置允许的来源。
- 播放失败只影响预览，不阻止 Camera 配置列表、详情或编辑。

## 10. Fixture

必须提供 `MediaGatewayStub`：

- 立即 `AVAILABLE`。
- 首次不可用、第二次 `AVAILABLE`。
- 持续不可用。
- 超时、503 和无效响应。
- 配置指纹变化后重建。
- 释放成功、资源已不存在和释放失败。

前端播放器 Fake 必须能断言创建次数、PeerConnection 关闭和媒体轨道停止。

## 11. 独立验收

1. Playback API 返回不含凭据的 WHEP URL，浏览器直连 MediaMTX。
2. MediaMTX Path `name` 直接等于 `source_id` UUID，不添加前缀或后缀。
3. 连接配置变化后使用新指纹更新映射。
4. 404、Path 不可播放、媒体服务不可用和无效响应均映射为稳定错误。
5. 列表只为可见卡片创建会话，离开后完整释放。
6. 详情开始、停止、页面隐藏和默认源切换均无会话泄漏。
7. 停止预览不发任何配置写请求。
8. MediaMTX 停机时 Camera 配置读取和编辑仍正常。
9. 日志与浏览器 PlaybackInfo 中找不到 RTSP 凭据。

## 12. Definition of Done

- Playback API、MediaMTX Adapter、投影端口和错误映射已实现。
- 列表懒加载与详情显式播放器已实现并能彻底释放资源。
- 后端 Stub、前端播放器 Fake 和依赖故障测试齐全。
- 尽力释放的 MVP 限制在实现说明中记录。
