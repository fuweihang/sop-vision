# Cameras MVP 剩余计划

已实现能力和当前约束见 [Cameras 模块文档](../../modules/cameras/README.md)。本目录不得复制这些
当前事实；计划执行时以模块文档、代码、迁移、OpenAPI 和测试为输入。

## 执行顺序

| #   | 任务                                                      | 状态   | 主要交付                     |
| --- | --------------------------------------------------------- | ------ | ---------------------------- |
| 09  | [更新与默认源](09-camera-update-default-source/README.md) | 待实施 | 编辑 Camera 和切换默认预览源 |
| 10  | [Camera 删除](10-camera-delete/README.md)                 | 待实施 | 删除聚合并尽力释放媒体 Path  |
| 11  | [发布门禁](11-release-gates/README.md)                    | 待实施 | 故障、安全、容量和端到端验收 |

顺序表达完成依赖。单个任务过大时可以继续拆成可独立实现和验证的子任务，但拆分文件仍放在对应
任务目录内。

## 剩余交付

在现有 Cameras 能力之上，本计划继续实现 Camera/Source 完整编辑、持久化默认预览源切换、Camera
删除，以及真实依赖、故障、安全、浏览器和容量验收。

本计划不包含鉴权、RBAC、多租户、录像、截图、回放、Detection WebSocket、检测 Canvas、视频帧与
Box 同步、WebRTC 质量统计、软删除和事务级 Outbox/Saga。

任务完成后的文档处理遵循 [执行计划完成规则](../README.md#完成规则)。
