# 08｜Camera 列表与 Cards 预览

> 前置：[创建](../05-camera-create/README.md)、[Stream Gateway Adapter](../03-stream-gateway-adapter/README.md)、[Playback](../07-source-playback/README.md)
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

## Cards 与恢复

- 路由 `/cameras`，URL 保存 `q/page/page_size`；搜索防抖 `300ms`，改变 q 后回到第一页。
- `total=0` 且无 q 显示空数据和创建入口；存在 q 时显示搜索无结果和清除操作。
- 首次加载使用骨架；页面可见时每 `15s` 后台刷新，保留旧 Cards；页面隐藏时暂停。
- Card 进入视口且 `whep_url` 非空时直接建立 WHEP，会话离开视口、切页或搜索变化时释放。
- `whep_url=null` 时默认不创建播放器。仅 `MTX_PATH_NOT_FOUND` 可按 Playback 契约自动恢复一次；
  真实离线或 Control API 故障不能触发逐 Card 重试风暴。
- 同一卡片不能并行创建多个播放器或恢复请求；列表正常路径不存在逐 Card FastAPI Playback 请求。
- 列表只使用内存 Query cache；所有配置写入成功后按公共缓存矩阵失效。

## 验收

- 默认参数返回前 20 条；名称/IP、空搜索、稳定分页和越界页语义正确。
- `%/_/\` 按普通字符搜索，额外查询参数不改变固定顺序。
- 无数据与搜索无结果界面不同，URL 可恢复搜索和分页。
- 一页无论多少 Source 只取一次 Path 快照；Control API 故障仍返回配置和确定降级状态。
- 在线 Cards 直接使用列表 URL；Path 丢失只恢复可见默认 Source；离线 Cards 不循环请求。
- 列表不泄密；不可见 Card 和卸载组件不保留播放器会话。
