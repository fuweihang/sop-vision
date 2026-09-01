# SOP Vision 文档

`docs/` 保存读者在当前版本仍需要的信息。代码、数据库迁移、生成契约和自动化测试是实现行为的
最终依据；文档负责解释能力边界、使用方式和重要原因。

## 从哪里开始

1. [仓库 README](../README.md)：运行方式、开发命令和项目现状。
2. [总体架构](vision-platform-architecture.md)：服务边界和目标演进方向。
3. [模块文档](modules/README.md)：已经实现并需要长期维护的业务与技术能力。
4. [技术决策](decisions/README.md)：跨模块且长期有效的取舍及原因。
5. [Design System](design-system/README.md)：前端视觉、布局和交互规则。
6. [执行计划](plans/README.md)：尚未完成、可以直接执行的任务。
7. [变更记录](changes/README.md)：已经交付的行为与兼容性影响。

## 目录职责

| 路径                     | 保存内容                                               | 不保存什么                 |
| ------------------------ | ------------------------------------------------------ | -------------------------- |
| `modules/`               | 已实现模块的能力、边界、接口、配置、故障行为和验证入口 | 待办步骤、完成进度         |
| `plans/`                 | 尚未完成工作的目标、范围、步骤、依赖和验收条件         | 已完成能力的长期说明       |
| `changes/`               | 每次有效交付带来的行为、API、配置、数据和兼容性变化    | 逐文件 diff、开发流水账    |
| `decisions/`             | 跨模块、长期有效且修改成本较高的技术决定               | 模块内部实现细节、临时讨论 |
| `design-system/`         | 当前 UI 规则、Token、组件和页面模式                    | 单个页面的实施计划         |
| `prototype/`             | 早期交互参考和设计证据                                 | 当前实现事实               |
| `assets/`、`references/` | 被其他文档引用的图片和外部资料                         | 独立的产品或技术规则       |

顶层的 `product-requirements.md`、`vision-platform-architecture.md` 和
`realtime-detection-design.md` 暂时保留原路径，后续发生实质修改时再分别迁入产品、架构或模块
目录，避免只为目录整齐制造无意义 diff。

## 文档生命周期

```text
需求或问题
   ↓
plans/<工作项>/        执行期间持续更新
   ↓ 完成并验证
modules/<模块>/        写入当前能力和长期约束
changes/<日期>-<主题>  记录这次交付改变了什么
   ↓
删除已完成 plan        Git 历史保留执行过程
```

只有跨多个模块、未来仍可能反复追问“为什么这样做”的决定，才额外写入 `decisions/`。同一条规则只
保留一个所有者，其他文档使用链接引用。

## 新增或修改文档

- 开始开发前，在 `plans/<工作项>/` 写可执行计划；小改动无需为了流程强建 plan。
- 开发完成时，先更新对应 `modules/<模块>/`，再写 `changes/`，最后删除完成的 plan。
- 修改 API、数据库、配置或安全边界时，长期文档必须说明兼容性和升级影响。
- 文档只写当前事实，不维护测试通过数量、手工更新时间和提交列表。
- 文件名使用小写 kebab-case；目录入口统一使用 `README.md`；链接优先使用相对路径。
- 出现冲突时按代码与迁移、生成契约、自动化测试、模块文档、计划与原型的顺序判断。

## 当前长期文档

- [Cameras](modules/cameras/README.md)：Camera 配置、创建、列表与详情、MediaMTX 对账和 WHEP 播放能力。
- [Backend 日志](modules/backend-logging/README.md)：统一输出、业务事件、HTTP access 与数据库日志。
- [总体架构](vision-platform-architecture.md)：当前服务与数据边界。
- [产品范围](product-requirements.md)：产品对象、计划能力和范围外事项。
- [实时检测数据设计](realtime-detection-design.md)：尚未实现的 Detector、Redis 和 WebSocket 目标设计。
- [Design System](design-system/README.md)：前端共享 UI 规则。
