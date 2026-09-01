# Camera 列表

> 相关文档：[Cameras 基础能力](foundation.md)、[Stream Gateway](stream-gateway.md)、
> [Camera 详情](camera-detail.md)

## 职责与边界

`GET /api/v1/cameras` 返回可供列表页面使用的非敏感 Camera 摘要。接口支持名称或 IPv4 字面包含
搜索，并按 `created_at ASC, camera_id ASC` 稳定分页。Backend API、OpenAPI、Frontend 生成类型、
MSW 场景和 `/cameras` 页面共同提供带实时预览 Card 的搜索分页能力。

列表响应只包含 Camera ID、名称、IPv4、RTSP 端口、聚合状态、Source 计数、默认 Source 摘要和创建/
更新时间。不会返回用户名、密码、Source 后缀、完整 RTSP URL 或完整 Source 数组。

## 查询参数

| 参数        | 默认值 | 规则                                 |
| ----------- | ------ | ------------------------------------ |
| `q`         | 无     | trim 后最长 100 字符；空白等同未提供 |
| `page`      | `1`    | 大于等于 1                           |
| `page_size` | `20`   | 1–100                                |

搜索对 Camera 名称和 IPv4 不区分大小写。`%`、`_` 和 `\` 按普通字符匹配，不作为 SQL 通配符；额外
查询参数会被忽略。越界页返回空 `items` 和真实 `total`。

## Backend 行为

列表用例在同一个请求级 Unit of Work 中先 count，再读取当前页完整聚合。两次数据库查询后显式
rollback 结束只读事务，之后才访问 MediaMTX，避免等待外部网络时继续占用 PostgreSQL 事务。

- 空页直接返回，不读取 MediaMTX。
- 非空页把当前页全部 Source 合并为一批，只读取一次 Runtime Path 快照。
- MediaMTX 不可用或响应无效时仍返回 `200`；当前页所有 Source 使用同一个失败时间和对应离线错误。
- 只有严格在线的默认 Source 返回 `whep_url`，离线默认 Source 不会改用其他 Source 的播放地址。
- 列表不会创建、修复或释放 MediaMTX Path。
- 当前页任一持久化聚合损坏时返回脱敏的 `500 CAMERA_AGGREGATE_INVALID`，不返回部分结果，也不
  访问 MediaMTX。错误和日志不包含损坏 Camera 的 ID、字段、凭据或 Source 后缀。
- 数据库查询或结束事务失败时返回 `503 DATABASE_UNAVAILABLE`；非法查询参数返回 `422`。

成功响应不设置 `Cache-Control: no-store`，但 Frontend 只能把结果保存在当前会话的内存 Query
cache 中，不得写入持久化浏览器存储。

## Frontend 页面

`/cameras` 的 `q/page/page_size` 由 Cameras 父路由使用 Zod 4 校验，列表和详情共同继承。搜索输入
防抖 300ms 后用 replace 更新 URL 并返回第一页；分页使用正常历史记录。Card 详情 Link、详情返回和
Cameras Breadcrumb 都携带完整查询参数，因此直接访问详情或使用浏览器前进/后退也能恢复列表位置。

列表 route loader 使用 `ensureQueryData` 等待首屏数据，页面使用相同 Query Options 的
`useSuspenseQuery` 订阅。页面可见时每 15 秒刷新，后台刷新期间保留已有 Cards 且不显示临时状态行，
避免 Grid 周期性位移；后台失败时保留 Cards 并显示非阻塞错误提示。初始网络错误和可信数据库 503
最多自动重试一次，仍失败时可由页面错误状态重新执行 loader。

页面分别显示无 Camera、搜索无结果和页码越界。越界页保留 API 的真实 `page/total`，只提供显式返回
第一页或上一页的 Link，不自动跳转。分页仅包含上一页、当前页/总页数和下一页。Card 只读取列表摘要，
展示 Camera 名称、IPv4/端口、Camera 状态、默认 Source 名称和在线计数，不读取敏感详情。Card 整体
是详情 Link；媒体区只消费列表摘要中的默认 Source。实时状态、空 WHEP URL、共享 Session 和 Lease
生命周期统一由 [WHEP 浏览器播放](whep-player.md#camera-card-行为)维护。

列表页沿用原型的紧凑工具栏，不显示额外页面标题和说明。搜索框与“添加摄像头”按钮保持同一行，
搜索框保留无障碍名称但不显示视觉标签。URL 缺少 `page_size` 时，Frontend 在首个 loader 请求前按
首次视口的 4/2/1 列布局选择 `12/6/4`，并把结果写入 URL；URL 已提供该参数时保持原值，窗口变化也
不会自动改页，避免分页内容、详情返回位置和浏览器历史随 resize 变化。显式非法值仍恢复为 Backend
默认的 `20`。

## 日志与排查

持久化聚合损坏记录 `camera.list_aggregate_invalid`，组件为 `camera.list`、级别为 ERROR，只允许
`operation` 和 `outcome` 字段。数据库 503 先检查 PostgreSQL；接口正常返回但状态全部离线时检查
MediaMTX Control API，不要把媒体降级误判为配置读取失败。
