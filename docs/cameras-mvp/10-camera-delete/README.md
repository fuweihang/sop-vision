# 10｜删除 Camera

> 前置：[详情](../06-camera-detail/README.md)、[媒体对账](../04-media-reconciliation/README.md)、[Playback](../07-source-playback/README.md)
>
> 交付：`DELETE /api/v1/cameras/{camera_id}`（`deleteCamera`）和危险操作确认

## 删除语义

用户从详情页二次确认后删除 Camera。除资源存在性外没有业务前置条件：在线状态、浏览器预览和
MediaMTX 映射都不阻止删除。本阶段没有软删除、恢复、批量删除、审批或跨业务引用保护。

后端锁定最新 Camera 并记录 Source ID，在同一事务中先显式删除全部 Source，再删除 Camera。
任一步失败完整回滚。数据库提交成功后，对每个 Source 尽力调用 `release_path`，清理总等待上限
`2s`；失败或进程崩溃不改变无 body 的 `204`，后台对账继续清理数据库已不存在的受管 UUID Path。

已不存在 Camera 返回 `404 CAMERA_NOT_FOUND`；数据库不可用返回
`503 DATABASE_UNAVAILABLE`。本切片不返回占用冲突或“删除中”状态。

删除与 Playback 并发时，Playback 必须在远端写入前确认 Source 当前存在；即使晚到请求仍重建
Path，下一轮对账也必须识别为孤儿并删除，不能复活数据库 Camera。

## 前端与可观测性

- 删除入口只在详情危险区；确认框显示 Camera 名称和 Source 数量，并明确不可恢复。
- 取消、关闭或 Escape 不删除；提交期间禁用确认和关闭，防止重复请求。
- 发请求前正常停止当前播放器；失败保留详情并允许重试。
- 成功后移除当前 `camera` 和所属 `playback` 内存数据，失效 `cameras`，再导航 `/cameras`。
- 日志和指标记录 trace ID、Camera ID、Source 数、数据库结果和释放结果，不记录凭据、RTSP URL
  或媒体敏感响应。

## 验收

- 单/多 Source、在线和正在预览的 Camera 均可删除并返回 `204`。
- 事务失败后完整聚合仍存在；媒体释放失败后数据库记录仍不存在且响应仍为 `204`。
- 覆盖 Camera 不存在、数据库失败、释放超时、进程崩溃窗口和下轮对账清理。
- 覆盖删除/Playback 并发，证明晚到 Path 最终被删除且 Camera 不会复活。
- Frontend 成功后关闭播放器、清理缓存并返回列表；所有日志和错误保持脱敏。
