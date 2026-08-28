# SOP Vision Design System

本目录记录 SOP Vision 前端的全局设计规则。组件视觉和 primitive 行为以 shadcn/ui `base-nova`
实现为准；原型只能作为布局和响应式意图的参考，不能在这里定义业务字段、操作或流程。

## 实现档案

- React、Vite、Tailwind CSS。
- TanStack Router。
- shadcn/ui `base-nova`、Base UI、Hugeicons。
- Light/Dark CSS Variables。
- UI 源码：`frontend/src/components/ui/`。
- 主题真源：`frontend/src/index.css`。

## 阅读顺序

1. [`catalog.json`](./catalog.json)：唯一机器入口、真源顺序和文件职责。
2. [`agent-guidelines.md`](./agent-guidelines.md)：Agent 执行规则。
3. [`specs/foundations.md`](./specs/foundations.md)：视觉原则。
4. [`specs/components.yaml`](./specs/components.yaml)：组件清单和项目级使用决策。
5. [`specs/layout.yaml`](./specs/layout.yaml)：Shell、Grid、Breakpoint 和 Reflow。
6. [`specs/page-patterns.md`](./specs/page-patterns.md)：可复用页面结构和共享状态。
7. [`specs/interaction-accessibility.md`](./specs/interaction-accessibility.md)：交互和可访问性。
8. [`tokens/`](./tokens/)：运行时主题快照和布局 token。
9. [`evidence/manifest.json`](./evidence/manifest.json)：仓库内可读取的设计证据。

## 真源优先级

面向人的简化顺序：

1. 当前用户指令和项目明确需求。
2. 前端 shadcn 配置、运行时主题和 UI 源码。
3. 本 Design System。
4. 已批准参考中的布局与响应式意图。
5. 可读取的 Evidence。

机器流程必须读取 `catalog.json#sourceOfTruthOrder`，其他文档不再重复定义完整顺序。

## 文件职责

| 文件          | 只负责                                          |
| ------------- | ----------------------------------------------- |
| Foundations   | 稳定视觉原则，不保存精确组件尺寸                |
| Components    | 项目用途、允许的 API 和例外，不复述 TSX anatomy |
| Layout        | Shell、层级、断点、Grid、滚动和 Reflow          |
| Page Patterns | 可复用页面结构、Section 排列和共享页面状态      |
| Interaction   | 键盘、焦点、表单、Dialog 和可访问性             |
| Tokens        | 主题审计快照与非颜色布局数值                    |
| Evidence      | 仓库中真实存在且可读取的证据                    |

## 原型边界

`docs/prototype/v1.0.html` 是静态原型，不是 shadcn 实现或业务需求文档。不得复制其中手写的
Button、Select、Dialog、Switch、Sidebar、SVG Icon 或 Hash Router；React 实现使用已安装组件、
Hugeicons 和 TanStack Router。原型中的字段、操作、状态流转和模拟数据不进入本目录。

## Token 边界

- `runtime-theme.tokens.json` 是 `frontend/src/index.css` 的审计快照，不能覆盖运行时主题。
- `layout.tokens.json` 保存 spacing、radius、size、breakpoint、layer 和 motion。
- 前端当前不直接消费这些 JSON；组件继续使用 shadcn/Tailwind 语义类。

## 内容边界

本目录只维护全局视觉原则、组件选择、App Shell、可复用页面结构、Light/Dark、键盘操作和响应式
Reflow。以下内容必须放在对应模块文档、产品需求或实施计划中：

- 具体路由、字段、表格列和文案；
- 业务状态枚举、转换条件和按钮可用性；
- 特定资源的功能流程和运行规则；
- 领域对象关系、协议、权限和数据校验；
- 单一页面或单一业务专用的交互细节。
