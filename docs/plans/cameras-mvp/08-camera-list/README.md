# 08｜Camera 列表与 Cards 预览

> 前置：[Camera 创建](../../../modules/cameras/camera-create.md)、
> [Stream Gateway](../../../modules/cameras/stream-gateway.md)、[WHEP 播放基础](../07-whep-player/README.md)
>
> 交付：`GET /api/v1/cameras`（`listCameras`）和 Camera Cards

## 响应与查询

用户可以按名称或 IPv4 搜索、分页浏览 Camera，并进入详情。配置读取不依赖媒体成功；外部投影
失败时列表仍返回 `200`。

响应为 `{items, page, page_size, total}`。每个 `CameraSummary` 包含：

| 字段                                  | 说明                                             |
| ------------------------------------- | ------------------------------------------------ |
| `camera_id/name/ip_address/rtsp_port` | 非敏感配置摘要                                   |
| `status`                              | `ONLINE/OFFLINE/DEGRADED`                        |
| `online_source_count/source_count`    | 在线数和配置总数                                 |
| `default_preview_source`              | `source_id/name/status/last_checked_at/whep_url` |
| `created_at/updated_at`               | UTC 时间                                         |

列表严禁返回 `username/password/url_suffix/rtsp_url`。

- `q` trim 后对名称和 IPv4 做大小写无关的字面包含搜索；空白等同未提供。
- 先搜索和 count，再按 Foundation 固定顺序分页；越界页返回空 `items` 和真实 `total`。
- 当前页全部 Source 共享一次完整 Path 快照，不得按 Camera 或 Source 调用 Control API。
- 严格在线的默认 Source 返回 `whep_url`；其他情况为 `null`。读取不创建或修复 Path。
- 数据库不可用返回 `503 DATABASE_UNAVAILABLE`；非法分页返回 `422`；额外查询参数被忽略。

## Cards 与共享播放

- 路由 `/cameras`，URL 保存 `q/page/page_size`；搜索防抖 `300ms`，改变 q 后回到第一页。
- `total=0` 且无 q 显示空数据和创建入口；存在 q 时显示搜索无结果和清除操作。
- 首次加载使用骨架；页面可见时每 `15s` 后台刷新，保留旧 Cards；页面隐藏时暂停。
- `CameraCard` 复用 07 的 `useStreamSession` 和 `VideoSurface`，使用 `object-fit: cover`；Card 只增加
  现有列表响应可提供的设备名称、在线状态和 LIVE HTML overlay，不复制 WHEP 或 video 生命周期
  代码。告警与检测概要等待 Detection 数据来源，不在 08 添加模拟字段。
- Card 进入视口且 `whep_url` 非空时，以默认 Source 的 `source_id` acquire；离开视口、切页或搜索
  变化时 release。短暂滚动抖动使用 IntersectionObserver 的可见阈值解决，不增加固定冷却计时器。
- `whep_url=null` 时不 acquire，也不渲染一个无媒体来源的 video。
- 同一 Source 同时出现在 Card 和 Detail 时，共享一个 `WhepSession` 和 `MediaStream`；各自保留独立
  video DOM、muted/volume 和 overlay。Card 始终静音且不显示详情 controls。
- 页面隐藏时释放全部 Card Lease；恢复时只为重新进入视口的 Card acquire。
- 列表只使用内存 Query cache；所有配置写入成功后按公共缓存矩阵失效。

## 验收

- 默认参数返回前 20 条；名称/IP、空搜索、稳定分页和越界页语义正确。
- `%/_/\` 按普通字符搜索，额外查询参数不改变固定顺序。
- 无数据与搜索无结果界面不同，URL 可恢复搜索和分页。
- 一页无论多少 Source 只取一次 Path 快照；Control API 故障仍返回配置和确定降级状态。
- 列表批量组装复用 Cameras Application 共享状态聚合，并覆盖全在线、全离线和混合 Camera，不在
  Stream Gateway 或列表 Router 复制聚合规则。
- 在线 Cards 直接使用列表 URL；离线 Cards 不 acquire。
- 多个消费者复用同一 Source 时只有一个 reader；释放一个 Card 不停止仍被其他消费者使用的 Track。
- 列表不泄密；不可见 Card 和卸载组件不保留 Lease，最后一个消费者释放后 Session 缓存为空。
