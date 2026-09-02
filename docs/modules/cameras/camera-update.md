# Camera 更新与默认预览源

> 相关文档：[Cameras 基础能力](foundation.md)、[媒体对账](media-reconciliation.md)、
> [Camera 详情](camera-detail.md)、[WHEP 浏览器播放](whep-player.md)

## 职责与边界

当前支持两个写入口：

- `PUT /api/v1/cameras/{camera_id}` 完整替换 Camera 可变连接配置和 Source 集合，成功返回最新
  `CameraDetail`。
- `PATCH /api/v1/cameras/{camera_id}/default-preview-source` 只切换默认预览 Source，成功返回
  `camera_id/default_preview_source_id/updated_at`。

字段、聚合、事务和敏感数据公共规则继续以 [Cameras 基础能力](foundation.md) 为准。Camera 删除尚未
实现；更新和默认源切换不会代替删除，也不提供局部 Source 更新、批量编辑或自动保存。

## Backend 行为

### 完整更新

PUT 锁定目标 Camera 及其 Source，在一个 PostgreSQL 事务内完成聚合读取、领域更新、完整保存和
提交：

- 有 `source_id` 的请求项必须属于当前 Camera，并保留既有 Source 身份和创建时间。
- 无 `source_id` 的项由服务端生成新 ID；请求中缺失的旧 Source 被删除。
- 请求数组顺序成为连续 `sort_order`，并且必须恰好选择一路默认 Source。
- Camera ID 和创建时间保持不变；Camera 与实际变化的 Source 更新时间使用同一次服务端时钟结果。
- 保存或提交失败会回滚完整事务，不会留下部分连接字段、Source 顺序或默认 ID。

提交成功后才计算并同步 MediaMTX 的实际变化：新增 Source、连接字段或后缀变化执行 `ensure_path`，
删除 Source 执行 `release_path`；只修改 Camera/Source 名称、顺序或默认标记不会重载 Path。单项媒体
写入或快照失败不会回滚已经提交的配置，其余项继续处理，本次响应使用降级运行态；后台对账会在
下一轮按 PostgreSQL 中的最终配置恢复缺失、漂移或孤儿 Path。

成功响应为 `200 CameraDetail` 并包含 `Cache-Control: no-store`。完整字段和错误响应以
[`contracts/openapi.json`](../../../contracts/openapi.json) 为准。

### 默认预览源

PATCH 与 PUT 使用相同的 Camera → Source 行锁顺序。目标 Source 必须属于当前 Camera，但不要求在线；
写入只改变 `default_preview_source_id` 和 Camera `updated_at`，不修改 Source 配置、顺序、时间或
MediaMTX Path，也不读取媒体运行态。

同一 Camera 的 PUT/PUT 和 PUT/PATCH 会按数据库锁串行。后取得锁的合法请求基于前一个已提交聚合
继续执行，因此最终数据库状态对应最后完成的合法更新。

### 失败边界

- Camera 不存在返回 `404 CAMERA_NOT_FOUND`。
- 字段、唯一默认、Source 所有权或后缀冲突返回 `422 VALIDATION_ERROR` 和对应字段路径。
- 已保存聚合无法重建时返回脱敏的 `500 CAMERA_AGGREGATE_INVALID`。
- 必需的数据库操作失败返回 `503 DATABASE_UNAVAILABLE`。

数据库提交结果未知时不会自动重发写请求。PUT 提交后的 MediaMTX 故障属于已保存配置的运行态降级，
不改写成数据库失败。

## Frontend 行为

详情页“编辑摄像头”打开完整编辑 Dialog，可以修改连接字段，新增、删除和上下移动 Source，并选择
唯一默认源。Dialog 打开后的 15 秒详情刷新不会覆盖当前草稿；存在未保存修改时，关闭 Dialog、应用
内路由离开和浏览器刷新/关闭都会要求确认。提交期间禁用表单、关闭和重复提交。

PUT 和默认源 PATCH 都设置 `retry=false`、`gcTime=0`，且不做乐观更新。成功后重新读取列表和详情，
不会把含密码、后缀和完整 RTSP URL 的 PUT 响应直接写入 Query cache。Mutation 完成后立即清除
variables 和结果。

Frontend 将 `404 CAMERA_NOT_FOUND`、`422 VALIDATION_ERROR` 和
`500 CAMERA_AGGREGATE_INVALID` 视为确定失败。网络错误、无法识别的响应、
`503 DATABASE_UNAVAILABLE` 和其他服务端 `5xx` 都视为“结果未知”：

- PUT 保留草稿并立即重新读取列表与详情；重新读取不会覆盖草稿或自动判定上一请求成功。再次保存前
  必须明确确认会发送一条新的完整 PUT。
- PATCH 保持提交前的单选值并重新读取列表与详情；用户仍可再次选择一个明确目标。

详情 Source 表格中的默认源单选可以选择离线 Source。它只控制列表 Card 使用哪一路默认 Source；
Detail 继续按保存顺序选择第一路可播放 Source，并保留仍可播放的临时选择，因此 PATCH 不会替换当前
详情流或重建无关 Lease。播放器的完整选择与生命周期规则见
[WHEP 浏览器播放](whep-player.md)。

## 排查

- 保存后页面仍显示旧配置时，先检查 PUT 是否成功，再检查随后的列表和详情 GET；Frontend 以重新
  读取结果为准，不消费 PUT 响应更新页面。
- 页面提示“更新结果未知”时，不要把重新读取失败当作写入失败，也不要直接重复请求；先确认数据库
  最终状态，再决定是否使用当前草稿再次完整覆盖。
- 配置已更新但 Source 运行态异常时，检查 MediaMTX 即时同步日志和后台对账状态；不要回滚或手工
  修改数据库中已提交的 Camera 配置。
- 默认源已变化但 Detail 仍播放原流属于预期行为；检查列表 Card 是否在重新读取后跟随默认源。
