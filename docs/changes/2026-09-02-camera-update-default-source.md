# 2026-09-02｜Camera 完整更新与默认预览源

## 变化

- 新增可用的 `PUT /api/v1/cameras/{camera_id}`，可以在一次请求中替换 Camera 连接字段和
  Source 集合，包括新增、删除、改名、后缀、顺序和默认标记。
- 新增可用的 `PATCH /api/v1/cameras/{camera_id}/default-preview-source`，可单独选择任何属于
  Camera 的 Source 作为列表 Card 默认预览源，包括当前离线的 Source。
- Camera 详情页现在可打开编辑 Dialog，修改连接信息、Source 集合、顺序和默认源；Source
  表格也可直接切换默认源。未保存修改会阻止误关闭或路由离开。
- Detail 的播放源不跟随默认源：自动选择按保存顺序的第一路可播放 Source，并保留仍可播放
  的当前页临时选择。

## 影响

- API 增加上述两个可用写行为，已同步受控 OpenAPI、Frontend 生成类型、Client、Fixture 和
  MSW 场景。没有新增路由或字段。
- 数据库没有新迁移；PUT 与 PATCH 使用既有完整聚合事务和 Camera 行锁。
- 没有新环境变量、MediaMTX 协议或部署配置。PUT 只在数据库提交后同步实际变化的
  Path；即时媒体失败由后台对账按数据库最终状态恢复。
- 写请求结果未知时不会自动重发。Frontend 会重新读取列表与详情，PUT 仍保留当前
  草稿并要求用户确认后才能再次完整覆盖。

Camera 删除仍未实现。真实 MediaMTX 重启、进程崩溃、多实例、目标 IPC/Codec、HTTPS/NAT、
长时间连接和容量验收仍由 [Cameras MVP 发布门禁](../plans/cameras-mvp/11-release-gates/README.md)负责。

## 验证

通过独立 PostgreSQL 的完整更新、回滚和同 Camera 并发写入测试，受控 Stream Gateway 的精确媒体
差异与下一轮对账恢复测试，Frontend 草稿/结果未知/缓存/Lease 自动化测试，以及双路
synthetic RTSP/WHEP 浏览器验收。契约、敏感数据、静态检查和生产构建同时通过。

## 相关长期文档

- [Camera 更新与默认预览源](../modules/cameras/camera-update.md)
- [Camera 详情](../modules/cameras/camera-detail.md)
- [媒体对账](../modules/cameras/media-reconciliation.md)
- [WHEP 浏览器播放](../modules/cameras/whep-player.md)
