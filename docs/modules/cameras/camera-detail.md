# Camera 详情

> 相关文档：[Cameras 基础能力](foundation.md)、[Stream Gateway](stream-gateway.md)、
> [Camera 创建](camera-create.md)

## 职责与边界

当前详情能力通过 `GET /api/v1/cameras/{camera_id}` 返回一个 Camera 的完整连接配置、按保存顺序
排列的 Source，以及同一次 MediaMTX 快照得到的运行状态。Frontend `/cameras/$cameraId` 提供对应的
只读页面，并沿用应用外壳中的“返回摄像头列表”链接。

详情页使用 Backend 返回的 `whep_url` 解析并播放当前可用 Source；播放器行为与共享 Session 规则见
[WHEP 浏览器播放](whep-player.md)。编辑、切换默认源和删除仍是禁用控件，不会产生业务请求。完整
RTSP URL 只作为可换行的等宽普通文本展示，不是链接，也没有复制按钮或 Clipboard 调用。

## Backend 行为

详情用例先从 PostgreSQL 读取完整聚合，再明确结束只读事务，最后在事务外读取一次 MediaMTX
Runtime Path 快照。这样媒体请求等待期间不会继续占用数据库事务和连接。

- Camera 不存在时直接返回 `404 CAMERA_NOT_FOUND`，不访问 MediaMTX。
- 持久化数据无法重建合法聚合时返回脱敏的 `500 CAMERA_AGGREGATE_INVALID`，不访问 MediaMTX。
- 数据库读取或结束事务失败时返回 `503 DATABASE_UNAVAILABLE`。
- MediaMTX 不可用或响应无效时不让完整配置不可读；接口仍返回 `200 CameraDetail`，全部 Source 使用
  同一个失败完成时间和稳定的媒体错误状态。
- MediaMTX 正常时，全部 Source 使用同一份快照投影状态，并复用共享聚合函数计算 Camera 状态和在线
  数量。响应中的 Source 顺序与 PostgreSQL 聚合顺序一致。
- 成功响应始终包含 `Cache-Control: no-store`；精确响应字段以
  [`contracts/openapi.json`](../../../contracts/openapi.json) 为准。

路径参数只接受小写、带连字符的标准 UUID v4；其他形式返回 `422 VALIDATION_ERROR` 和
`camera_id/INVALID_UUID`。Camera、Source 状态、`error`、`last_checked_at`、`whep_url` 和完整
`rtsp_url` 的公共规则见 [Cameras 基础能力](foundation.md)与
[Stream Gateway](stream-gateway.md)。

## Frontend 行为

详情路由通过 `ensureQueryData` 预取，只把 Camera 名称返回给 Breadcrumb；完整详情遵守
[Cameras 敏感数据边界](foundation.md#敏感数据)，由页面使用相同 Query Options 订阅后续刷新。

| Query 设置                    | 当前值  |
| ----------------------------- | ------- |
| `staleTime`                   | 15 秒   |
| `gcTime`                      | 5 分钟  |
| `refetchInterval`             | 15 秒   |
| `refetchIntervalInBackground` | `false` |

页面可见时每 15 秒刷新，页面隐藏时暂停；后台刷新失败继续显示旧内容。网络失败或可信的
`503 DATABASE_UNAVAILABLE` 最多自动重试一次，404、422、损坏聚合、意外响应和程序错误不自动
重试。可信的 `404 CAMERA_NOT_FOUND` 进入专用未找到页面，其他错误进入 Cameras 路由错误页。

只读页面按以下顺序展示：

1. Camera 名称、可用的开始/停止预览按钮，以及禁用的编辑按钮；
2. 当前 Source 的 16:9 实时播放器和临时 Source Select；
3. IPv4、端口、用户名、默认隐藏的密码、默认 Source 最近检查时间，以及标题右侧的
   Camera 聚合状态 Badge；
4. “摄像头视频源”表格，按响应顺序展示禁用的默认源单选控件、名称、完整 RTSP URL 和状态 Badge；
5. 禁用的删除摄像头按钮。

密码使用固定星号占位，不显示实际长度；用户点击眼睛按钮后可以在当前页面显隐。页面不展示
`created_at/updated_at`。窄屏下连接信息与预览区域改为单列，视频源表格只在自身容器内横向滚动，
不扩大整个页面。默认/临时 Source 选择、预览意图、操作栏状态、错误恢复和 Lease 生命周期统一由
[WHEP 浏览器播放](whep-player.md#camera-详情行为)维护。

## 排查

- Browser MSW 只在显式开发场景启用，并关闭正常请求日志，避免详情响应进入开发终端。未声明业务请求
  仍报错；仅忽略常见静态资源和 Codex/Playwright 的 `/__tsd/console-pipe` 开发日志请求。
- 页面显示 404 时，先确认 URL 中 Camera ID 是标准 UUID v4，再确认 PostgreSQL 中聚合存在。
- 页面显示数据库错误时检查 PostgreSQL；若页面仍能打开但 Source 全部显示媒体服务不可用，则检查
  MediaMTX Control API 和 Stream Gateway，不要把它误判成 Camera 配置读取失败。
- 页面提示默认预览源无效表示返回数据没有匹配 `default_preview_source_id` 的 Source，应检查后端聚合
  与响应映射，Frontend 不会自行选择另一路 Source 掩盖数据问题。
- 页面提示当前视频源不可播放时检查详情响应的 `whep_url` 和 Source 状态；Frontend 不会自行拼接或
  修复 WHEP 地址。
