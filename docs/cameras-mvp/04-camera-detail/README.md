# 04｜Camera 详情

> 前置：[Cameras 基础契约](../01-foundation/README.md)  
> 交付：`GET /cameras/{camera_id}`、详情路由、Source 信息和凭据响应边界

## 1. 完成目标

用户可以通过独立 URL 查看一台 Camera 的基础信息、完整 Source 集合、默认预览源、连接状态和播放信息，并能够返回 Cameras 列表。

配置读取不依赖实时状态或 MediaMTX 可用性；这些投影失败时使用确定的降级值。

## 2. 范围

### 后端

- 按 `camera_id` 读取 Camera 聚合。
- 按 `sort_order` 返回全部 Source。
- 生成完整 RTSP URL。
- 合并 Source 状态和 WHEP 地址。
- 返回禁止缓存的敏感响应。

### 前端

- `/cameras/{camera_id}` 详情路由和“返回 Cameras”操作。
- 展示基础字段、默认源、Source 列表和状态。
- 提供编辑、切换默认源、预览和删除的入口容器；具体操作由各自文档实现。
- 覆盖加载、刷新、不存在和投影降级状态。

### 不属于本模块

- 修改任何 Camera 配置。
- MediaMTX Path 状态映射、播放协议或播放器内部实现。

## 3. API

```http
GET /api/v1/cameras/6f9619ff-8b86-4e4f-9f68-bb3f8f6f4f21
```

成功：

```http
HTTP/1.1 200 OK
Cache-Control: no-store
```

```json
{
  "camera_id": "6f9619ff-8b86-4e4f-9f68-bb3f8f6f4f21",
  "name": "洗手区 01",
  "ip_address": "192.168.1.64",
  "rtsp_port": 554,
  "username": "admin",
  "password": "camera-secret",
  "default_preview_source_id": "8f14e45f-ea9d-4a7d-9b6d-8c9f0a1b2c3d",
  "status": "DEGRADED",
  "online_source_count": 1,
  "source_count": 2,
  "sources": [
    {
      "source_id": "8f14e45f-ea9d-4a7d-9b6d-8c9f0a1b2c3d",
      "name": "通道 1 主码流",
      "url_suffix": "Streaming/Channels/101",
      "rtsp_url": "rtsp://admin:camera-secret@192.168.1.64:554/Streaming/Channels/101",
      "is_default_preview": true,
      "status": "ONLINE",
      "last_checked_at": "2026-08-19T03:00:00Z",
      "error": null,
      "whep_url": "https://vision.example.internal/media/8f14e45f-ea9d-4a7d-9b6d-8c9f0a1b2c3d/whep"
    },
    {
      "source_id": "3f2504e0-4f89-41d3-9a0c-0305e82c3301",
      "name": "通道 1 子码流",
      "url_suffix": "Streaming/Channels/102",
      "rtsp_url": "rtsp://admin:camera-secret@192.168.1.64:554/Streaming/Channels/102",
      "is_default_preview": false,
      "status": "OFFLINE",
      "last_checked_at": "2026-08-19T02:59:55Z",
      "error": "MTX_PATH_NOT_AVAILABLE",
      "whep_url": null
    }
  ],
  "created_at": "2026-08-01T03:00:00Z",
  "updated_at": "2026-08-18T06:20:00Z"
}
```

不存在：

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
```

错误 code 为 `CAMERA_NOT_FOUND`，`context.camera_id` 返回请求中的 ID。

## 4. 响应规则

- `sources` 始终按持久化顺序返回。
- `source_count` 等于 `sources.length`。
- `online_source_count` 只统计状态为 `ONLINE` 的 Source。
- 恰好一个 Source 的 `is_default_preview=true`，且其 ID 等于 `default_preview_source_id`。
- `rtsp_url` 每次由当前 Camera 连接字段和 Source 后缀生成，不单独持久化。
- Path 名称存在且 `available === true && online === true` 时 Source 为 `ONLINE`；其他组合为 `OFFLINE`。
- `/paths/list` 失败时全部 Source 返回 `OFFLINE` 和对应 Control API error code。
- `last_checked_at` 为本次完整 Path 快照成功或失败的完成时间。
- WHEP 未就绪或媒体服务不可用时返回 `whep_url=null`，不令详情请求失败。

配置聚合本身不满足至少一路 Source 或唯一默认源时，视为服务端数据损坏，返回 `500 CAMERA_AGGREGATE_INVALID` 并触发告警，不返回部分详情。

## 5. 凭据边界

当前 MVP 要求详情回填 `username/password/rtsp_url` 以支持编辑，因此：

- 响应必须设置 `Cache-Control: no-store`。
- 服务端和反向代理不得把响应写入共享缓存。
- 前端只在当前页面内存中保存详情，不写入 localStorage、IndexedDB 或离线缓存。
- 前端错误上报不得附带完整响应体。
- 页面隐藏或离开详情后，释放播放器；查询缓存按应用会话策略清理敏感详情。
- 服务端日志不得序列化 CameraDetail。

## 6. 后端处理流程

1. 读取 Camera 和按序 Source；不存在则返回 `404`。
2. 验证聚合约束。
3. 为每个 Source 生成 RTSP URL。
4. 读取一次完整 `/paths/list` 快照并批量映射 Source；失败时全部映射为 `OFFLINE`。
5. 批量或按默认源读取可用播放投影；失败时 `whep_url=null`。
6. 计算 Camera 聚合状态和在线数。
7. 返回详情和 `Cache-Control: no-store`。

状态与播放合并必须有总超时，不得无限延迟基础配置读取。MVP 默认投影总等待上限为 `500ms`，超时后降级返回。

## 7. 前端页面契约

- 首次进入显示详情骨架，不提前展示上一个 Camera 的数据。
- 后台刷新保留当前内容，并显示非阻塞刷新反馈。
- `404` 显示“摄像头不存在或已删除”和“返回 Cameras”。
- 页面标题或面包屑显示 Camera 名称，数据加载前显示稳定占位文本。
- Source 区域展示名称、完整 RTSP URL、是否默认、状态和最近检查时间。
- 默认源预览区域优先使用详情中的 `whep_url`；为 `null` 时展示未就绪。
- 编辑、切换默认源和删除成功后必须重新获取详情或离开页面。
- 复制 RTSP URL 属于显式用户操作；复制按钮需提示其中包含凭据。

## 8. 缓存

Query Key：

```text
["camera", cameraId]
```

- 浏览器 HTTP 缓存必须被 `no-store` 禁止。
- 应用内查询缓存不得持久化，可在当前会话短期保留以支持编辑返回。
- 更新或默认源切换后失效当前 `camera`。
- 删除后移除当前 `camera`，不得后台重试已删除资源。

## 9. Fixture

至少提供：

- 单 Source、多个 Source 和四种聚合状态。
- WHEP 正常、未就绪和媒体服务不可用。
- Control API 不可用、投影超时和 Camera 不存在。
- 固定凭据用于断言响应头、日志和前端持久化边界。

## 10. 独立验收

1. 直接访问详情 URL 可恢复页面，Source 顺序和默认源正确。
2. 成功响应包含 `Cache-Control: no-store`。
3. Source 状态或 MediaMTX 故障时基础详情仍返回 `200`。
4. 不存在 Camera 返回稳定 `404 CAMERA_NOT_FOUND`。
5. RTSP URL 由当前连接字段正确生成。
6. 日志、监控和前端持久化存储中找不到测试密码。
7. `404`、首次加载失败和后台刷新失败均有明确恢复操作。

## 11. Definition of Done

- 详情查询、聚合验证、投影合并、响应头和超时降级已实现。
- 详情路由、Source 展示、返回操作和错误状态已实现。
- 敏感数据边界有自动化测试。
- 可使用状态和播放 Fake 独立演示。
