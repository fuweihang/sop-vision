# 09｜更新 Camera 与切换默认源

> 前置：[Camera 详情](../../../modules/cameras/camera-detail.md)、
> [媒体对账](../../../modules/cameras/media-reconciliation.md)、
> [WHEP 浏览器播放](../../../modules/cameras/whep-player.md)
>
> 最终交付：`PUT /api/v1/cameras/{camera_id}`、
> `PATCH /api/v1/cameras/{camera_id}/default-preview-source` 和对应详情交互

09 同时跨越 Backend 完整更新、默认源写入、Frontend 编辑表单、路由离开保护、查询缓存和共享媒体
Session，不能作为一个开发任务一次性实施。按以下顺序拆成可独立审核、实现和验证的任务：

| #   | 任务                                                                        | 主要交付                                      |
| --- | --------------------------------------------------------------------------- | --------------------------------------------- |
| 01  | [Backend Camera 完整更新](01-backend-camera-update/README.md)               | PUT、事务、媒体 diff、CameraDetail 与错误响应 |
| 02  | [Backend 默认预览源切换](02-backend-default-preview-source/README.md)       | PATCH、默认 ID 原子保存与最小确认响应         |
| 03  | [Frontend Camera 编辑 Dialog](03-frontend-camera-edit/README.md)            | 完整编辑、排序、结果未知和未保存修改保护      |
| 04  | [Frontend 默认源与播放器联动](04-frontend-default-preview-source/README.md) | 默认源单选、缓存刷新和 Card/Detail Lease 切换 |
| 05  | [09 集成验收与文档收尾](05-integration-docs/README.md)                      | 跨端组合验收、长期文档、交付记录与计划移除    |

任务必须顺序执行。后续任务以已落地代码、迁移、OpenAPI、生成类型和测试为准，不能用前序计划中的实现
假设覆盖当前事实，也不能并行创建临时接口或重复规则。

## 共同交付范围

- PUT 完整替换 Camera 可变配置和 Source 集合：有 `source_id` 的项保留身份，无 ID 项新增，请求中
  缺失的旧项删除，数组顺序成为保存顺序，唯一默认标记成为默认 Source。
- PUT 在数据库事务提交后只同步实际变化的 MediaMTX Desired State；名称或排序变化不重载 Path，
  新增、后缀或连接字段变化执行 ensure，删除执行 release，媒体故障不回滚数据库结果。
- PATCH 只更新默认 Source ID 和 Camera `updated_at`。离线 Source 可以设为默认，不修改 Source
  配置、顺序或 MediaMTX Path。
- Frontend 编辑使用 Dialog，支持连接字段、Source 增删、上移/下移排序和默认源；打开后的详情轮询
  不覆盖表单，未保存修改在关闭、应用内路由和浏览器离开前确认。
- 默认源单选不做乐观更新。列表 Card 只跟随列表响应中的默认 Source；详情默认选择重新解析，临时
  选择仍可播放时保持不变。
- Card 或 Detail 只在实际 Source ID 或 `whep_url` 变化时切换 Lease；相同媒体来源不重建共享
  Session，最后一个引用释放后才关闭。

精确字段、事务、敏感数据和播放器公共规则继续以
[Cameras 基础能力](../../../modules/cameras/foundation.md)、
[Camera 详情](../../../modules/cameras/camera-detail.md)和
[WHEP 浏览器播放](../../../modules/cameras/whep-player.md)为准，各任务不维护第二份公共事实。

## 共同失败语义

- `404 CAMERA_NOT_FOUND`、`422 VALIDATION_ERROR` 和
  `500 CAMERA_AGGREGATE_INVALID` 是确定失败。
- Transport、无法识别或不符合契约的响应、`503 DATABASE_UNAVAILABLE` 及其他服务端 `5xx` 对
  Frontend 都是结果未知，因为数据库可能已经提交但成功响应没有到达。
- PUT 和 PATCH Mutation 都禁止自动重试。结果未知时保留当前表单或提交前选择，不做乐观更新，立即
  重新获取列表和详情；重新读取失败时继续提示结果未知，只有用户确认后才发送新的写请求。
- 请求、响应、Problem、日志、通知、追踪、错误上报和 Mutation cache 必须遵守现有密码、Source
  后缀和完整 RTSP URL 边界。

## 共同不做事项

- 不实现鉴权、RBAC、多租户、软删除、批量编辑、自动保存、跨页面草稿或拖拽排序。
- 不增加 ETag、版本比较、冲突解决 UI、幂等键、Outbox/Saga、Generic Repository 或通用 CRUD/
  Mutation 框架。
- 不修改 Camera 删除，不为默认源 PATCH 探测在线状态，不让 Frontend 直接访问 MediaMTX Control
  API。
- 09 只使用独立 PostgreSQL、可控 Stream Gateway/对账和现有 synthetic WHEP Source 做确定性验收。
  真实 MediaMTX 重启、进程崩溃、多实例、真实 IPC/浏览器/网络、长时间和容量继续由
  [11｜发布门禁](../11-release-gates/README.md)负责。

## 09 完成条件

只有 01–05 全部完成后，09 才算交付。任务 05 必须以实际实现为准更新 Cameras 模块文档，在
`docs/changes/` 新增交付记录，执行完整自动化与 synthetic 浏览器验收，再从上级剩余计划和文件
系统移除 09。任何必要测试失败或 PostgreSQL 集成测试跳过时都不能提前收尾。
