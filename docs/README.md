# SOP Vision 文档

本目录只保存对当前开发仍有长期价值的产品、架构、契约和设计约束。运行方法以仓库根
[README](../README.md) 为入口；精确实现行为以代码、迁移、生成契约和自动化测试为准。

## 项目现状

- Cameras Foundation 已完成并由测试、OpenAPI 生成和 CI 门禁保护。
- Cameras CRUD、Source 状态、WHEP 预览和删除仍只有目标契约，没有业务实现。
- Frontend 已具备 App Shell、路由、通用页面状态、API Client 与 MSW；业务页面仍是骨架。
- Compose 已包含 Redis，但 Backend 没有 Redis 客户端；Detector、Detection Tasks、
  WebSocket 和实时检测链路均未实现。

“路由已出现在 OpenAPI”只表示当前占位契约可供跨端生成，不表示对应 handler 可用。Playback 已
按准备/恢复语义冻结为 `POST prepareCameraSourcePlayback`，Router、OpenAPI、Frontend Client 和
MSW 使用同一契约；真实媒体恢复行为仍属于 Cameras 07 切片。

## 阅读顺序

1. [仓库 README](../README.md)：当前状态、运行方式和开发命令。
2. [总体架构](vision-platform-architecture.md)：已实现边界和目标演进方向。
3. [Cameras MVP](cameras-mvp/README.md)：当前实现进度、冻结规则和功能契约。
4. [Backend README](../backend/README.md) / [Frontend README](../frontend/README.md)：子项目开发。
5. [Design System](design-system/README.md)：前端视觉、布局和交互约束。

## 文档职责

| 文档                                                      | 性质        | 负责内容                                    |
| --------------------------------------------------------- | ----------- | ------------------------------------------- |
| [总体架构](vision-platform-architecture.md)               | 当前 + 目标 | 服务边界、数据职责、已实现与未实现链路      |
| [产品范围](product-requirements.md)                       | 产品基线    | 产品对象、计划能力、范围外事项和未决问题    |
| [Cameras MVP](cameras-mvp/README.md)                      | 冻结契约    | Camera 第一阶段范围、状态和功能切片         |
| [Cameras Foundation](cameras-mvp/01-foundation/README.md) | 已实现约束  | 数据、事务、HTTP、敏感数据和跨端基础        |
| [Design System](design-system/README.md)                  | 设计规范    | 当前 Shell 与计划业务页面的 UI 规则         |
| [实时检测数据设计](realtime-detection-design.md)          | 目标设计    | Detector、Redis、WebSocket 的通信语义与约束 |
| [交互原型](prototype/v1.0.html)                           | 参考产物    | 早期布局与业务流程，不代表当前实现或 API    |

`cameras-mvp/02–11` 是尚未实现的功能契约，不是完成记录。`prototype/` 和架构图是设计证据，
不得覆盖运行时代码、`components.json`、OpenAPI 或数据库迁移中的事实。

## 事实优先级

出现冲突时按以下顺序处理：

1. 当前代码、运行配置和数据库迁移。
2. `contracts/openapi.json` 及其生成测试。
3. 自动化测试中冻结的行为。
4. 对应领域的核心文档。
5. 原型、图示和目标设计。

不要在文档中维护测试通过数量、逐步实施记录或手工更新时间。Git 历史和 CI 负责记录过程；
文档只描述当前状态与长期约束。
