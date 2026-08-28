# Cameras MVP 剩余计划

> 当前状态：Camera 创建已经完成；本计划只跟踪详情、播放、列表、更新、删除和发布验收。

已实现能力和当前约束见 [Cameras 模块文档](../../modules/cameras/README.md)。本目录不得复制这些
当前事实；计划执行时以模块文档、代码、迁移、OpenAPI 和测试为输入。

## 执行顺序

| #   | 任务                                                      | 状态   | 主要交付                            |
| --- | --------------------------------------------------------- | ------ | ----------------------------------- |
| 06  | [Camera 详情](06-camera-detail/README.md)                 | 待实施 | `GET /cameras/{camera_id}` 与详情页 |
| 07  | [Source 播放准备](07-source-playback/README.md)           | 待实施 | 播放恢复命令和播放器生命周期        |
| 08  | [Camera 列表](08-camera-list/README.md)                   | 待实施 | `GET /cameras`、搜索、分页与卡片    |
| 09  | [更新与默认源](09-camera-update-default-source/README.md) | 待实施 | 编辑 Camera 和切换默认预览源        |
| 10  | [Camera 删除](10-camera-delete/README.md)                 | 待实施 | 删除聚合并尽力释放媒体 Path         |
| 11  | [发布门禁](11-release-gates/README.md)                    | 待实施 | 故障、安全、容量和端到端验收        |

顺序表达完成依赖。单个任务过大时可以继续拆成可独立实现和验证的子任务，但拆分文件仍放在对应
任务目录内。

## MVP 目标范围

完成本计划后，用户可以搜索和分页浏览 Camera，查看详情，完整编辑 Camera/Source 集合，切换默认
预览源，通过 WHEP 预览并删除 Camera。

本计划不包含鉴权、RBAC、多租户、录像、截图、回放、WebSocket 状态推送、软删除和事务级
Outbox/Saga。

## 完成任务时如何处理文档

每完成一个任务，同时执行以下动作：

1. 更新 `docs/modules/cameras/` 中对应的当前能力、边界和排障信息。
2. 在 `docs/changes/` 新增一条变更记录，说明用户可见行为、API/配置影响和验证方式。
3. 从本表和本目录移除已完成任务；不要在计划里长期维护“已完成”章节。
4. 如果形成跨模块且难以撤销的技术决定，再在 `docs/decisions/` 新增决策记录。

Git 历史保存执行过程，长期文档不保存逐步实施日志或测试通过数量。
