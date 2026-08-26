# 09｜删除 Camera

> 状态：目标契约已冻结，业务实现尚未开始。
>
> 前置：[Foundation](../01-foundation/README.md)、[详情](../04-camera-detail/README.md)
>
> 交付：`DELETE /api/v1/cameras/{camera_id}`（`deleteCamera`）和危险操作确认

## 删除语义

用户从详情页二次确认后删除 Camera。除资源存在性外没有业务前置条件：在线状态、浏览器预览
和 MediaMTX 映射都不阻止删除。本阶段没有软删除、恢复、批量删除、审批、跨业务保护或可靠
异步清理。

后端锁定最新 Camera 并记录 Source ID，在同一事务中先显式删除全部 Source，再删除 Camera。
任一步失败完整回滚。数据库提交成功后，对每个 Source 尽力调用 `release_source`，清理总等待
上限 `2s`；失败或进程崩溃可能留下可重建映射，但数据库删除仍返回无 body 的 `204`。

已不存在 Camera 返回 `404 CAMERA_NOT_FOUND`；数据库不可用返回
`503 DATABASE_UNAVAILABLE`。本切片不返回占用冲突或“删除中”状态。

## 前端与可观测性

- 删除入口只在详情危险区；确认框显示 Camera 名称和 Source 数量，并明确不可恢复。
- 取消、关闭或 Escape 不删除；提交期间禁用确认和关闭，防止重复请求。
- 发请求前正常停止当前播放器；失败保留详情并允许重试。
- 成功后移除当前 `camera` 和所属 `playback`，失效 `cameras`，再导航 `/cameras`。
- 日志和指标记录 trace ID、Camera ID、Source 数、数据库结果和释放结果，不记录凭据、RTSP URL
  或媒体敏感响应。

## 验收

- 单/多 Source、在线和正在预览的 Camera 均可删除并返回 `204`。
- 事务失败后完整聚合仍存在；媒体释放失败后数据库记录仍不存在且响应仍为 `204`。
- Camera 不存在、数据库失败和释放超时均有确定行为。
- 前端成功后关闭播放器、清理缓存并返回列表；所有日志和错误保持脱敏。
