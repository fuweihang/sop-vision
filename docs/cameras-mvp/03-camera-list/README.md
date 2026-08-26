# 03｜Camera 列表

> 状态：目标契约已冻结，业务实现尚未开始。
>
> 前置：[Foundation](../01-foundation/README.md)
>
> 交付：`GET /api/v1/cameras`（`listCameras`）和 Camera 卡片列表

## 目标与响应

用户可以按名称或 IPv4 搜索、分页浏览 Camera，并进入详情。配置读取不依赖状态或播放服务；
外部投影失败时列表仍返回 `200`。

响应为 `{items, page, page_size, total}`。每个 `CameraSummary` 包含：

| 字段                                  | 说明                                             |
| ------------------------------------- | ------------------------------------------------ |
| `camera_id/name/ip_address/rtsp_port` | 非敏感配置摘要                                   |
| `status`                              | `ONLINE/OFFLINE/DEGRADED`                        |
| `online_source_count/source_count`    | 在线数和配置总数                                 |
| `default_preview_source`              | `source_id/name/status/last_checked_at/whep_url` |
| `created_at/updated_at`               | UTC 时间                                         |

列表严禁返回 `username/password/url_suffix/rtsp_url`。

## 查询与投影

- `q` trim 后对名称和 IPv4 做大小写无关的字面包含搜索；空白等同未提供。
- 先搜索和 count，再按[Foundation 固定顺序](../01-foundation/README.md#持久化与事务)分页。
- 越界页返回空 `items` 和真实 `total`；额外参数（包括旧 `sort`）被忽略。
- 当前页所有 Source 共享一次完整 Path 快照，不得按卡片或 Source 调用 MediaMTX。
- 状态、聚合和 Control API 降级遵循[状态契约](../07-source-status/README.md)。
- 播放投影只读取现有 Path，不主动创建映射；不可用时 `whep_url=null`。

数据库不可用返回 `503 DATABASE_UNAVAILABLE`。非法分页返回 `422`；后台刷新失败保留旧内容。

## 前端

- 路由 `/cameras`，URL 保存 `q/page/page_size`；搜索防抖 `300ms`，改变 q 后回到第一页。
- `total=0` 且无 q 显示空数据和创建入口；存在 q 时显示搜索无结果和清除操作。
- 首次加载使用骨架；后台刷新保留卡片并显示非阻塞状态。
- 卡片展示名称、`IP:端口`、聚合状态、在线数和默认源预览区域。
- 预览仅在卡片可见时创建；离开视口、切页或搜索变化时释放；`whep_url=null` 不创建播放器。
- 列表只使用内存 Query cache；所有配置写入成功后按公共缓存矩阵失效。

## 验收

- 默认参数返回前 20 条；名称/IP、空搜索、稳定分页和越界页语义正确。
- `%/_/\` 按普通字符搜索，额外查询参数不改变固定顺序。
- 无数据与搜索无结果界面不同，URL 可恢复搜索和分页。
- 一页无论多少 Source 只取一次 Path 快照；Control API 故障仍返回配置和 `OFFLINE`。
- 列表不泄密；不可见卡片和卸载组件不保留播放器会话。
