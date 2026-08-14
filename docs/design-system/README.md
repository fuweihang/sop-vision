# SOP Vision Design System

本目录把 Vercel 后台的实测设计语言转译为 SOP Vision 可复用的设计规范。它服务于两类消费者：

- AI Design：理解视觉原则、布局模式、组件构成和状态约束。
- AI Coding：读取机器可解析的 token 和规格，生成一致的界面实现与测试。

这里记录的是基于 `1280 × 720`、浅色主题、登录后后台页面的观察与项目化决策，不是 Vercel 官方 API，也不应复制 Vercel 商标、文案或产品身份。

## 阅读顺序

1. [`catalog.json`](./catalog.json)：机器可读入口和文件职责。
2. [`specs/foundations.md`](./specs/foundations.md)：设计原则与视觉语言。
3. [`tokens/`](./tokens/)：基础 token、语义 token 和主题映射。
4. [`specs/layout.yaml`](./specs/layout.yaml)：布局尺寸与响应规则。
5. [`specs/components.yaml`](./specs/components.yaml)：组件 anatomy、variants 和 states。
6. [`specs/page-patterns.md`](./specs/page-patterns.md)：页面组合方式。
7. [`specs/interaction-accessibility.md`](./specs/interaction-accessibility.md)：交互与可访问性要求。
8. [`agent-guidelines.md`](./agent-guidelines.md)：Agent 的执行约束和验收清单。

## 真源优先级

发生冲突时按以下优先级处理：

1. 项目明确需求和用户指令。
2. `semantic.tokens.json` 与所选主题文件。
3. `components.yaml`、`layout.yaml` 和交互规范。
4. 页面模式与 foundations 文档。
5. `evidence/` 中的原始观察。

证据用于解释设计决策，不应直接变成业务组件里的硬编码值。

## Token 组合方式

构建某个主题时，应合并以下三个文件，然后解析 `{path.to.token}` 引用：

```text
primitives.tokens.json
+ semantic.tokens.json
+ light.tokens.json 或 dark.tokens.json
```

Token 使用 DTCG 风格的 `$type`、`$value` 和 `$description` 字段。实现层可以从合并结果生成 CSS Custom Properties、Tailwind theme、TypeScript 常量或其他框架映射，但生成物不应反向成为设计真源。

## 当前范围

已覆盖：

- 浅色和暗色主题的核心语义映射。
- 字体、颜色、间距、尺寸、圆角、阴影与动效。
- 可折叠固定侧栏后台、缩放时的 Drawer Shell、设置页和筛选列表页。
- Button、Input、Select、Card、Navigation、Badge、Popover、Empty State 等基础组件。
- Dialog 与 ROI 多边形编辑器 MVP。
- Hover、Focus、Disabled、Loading、键盘操作以及 200% 缩放 Reflow 要求。

尚未覆盖：移动端实测、复杂数据表格、图表颜色、高级编辑器、拖放和品牌插画。ROI 编辑器当前仅覆盖点击绘制与整体重绘 MVP，不包含顶点拖拽和键盘点位输入。
