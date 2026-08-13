# Agent Guidelines

## 任务开始前

1. 阅读 `catalog.json` 和本文件。
2. 确认任务属于基础样式、组件、页面模式还是新业务需求。
3. 选择 Light 或 Dark theme；没有明确要求时使用 Light。
4. 合并 primitives、semantic 和所选 theme token，再解析引用。
5. 在 `page-patterns.md` 中选择最接近的页面模式。

## AI Design 规则

- 先定义信息层级和交互状态，再决定视觉细节。
- 优先复用 `components.yaml` 中的组件和 variant。
- 只在现有语义无法表达需求时提出新 token，并说明为什么现有 token 不适用。
- 输出必须包含 Desktop 1280×720 首屏、窄屏降级、Empty/Loading/Error/Disabled 状态。
- 使用中性、紧凑、工程工具化的风格；避免大面积渐变、玻璃拟态、浓重阴影和无目的插画。
- 不复制 Vercel 标志、专有图标、产品名称或原始文案。

## AI Coding 规则

- 组件只能引用语义 token；禁止硬编码已存在于 token 中的颜色、间距、圆角和阴影。
- Primitive token 只用于构建设计系统，业务组件不得直接引用原始灰阶编号。
- 默认控件高度 36px，正文 14px，常用图标 16px，控件/卡片圆角 6px。
- 普通 Card 使用细轮廓而不是 elevation；阴影仅用于浮层。
- 所有交互组件实现 Default、Hover、Active、Focus Visible、Disabled；异步操作增加 Loading 和 Error。
- 保留原生语义元素；只有原生语义不足时才增加 ARIA。
- 新组件应补充组件规格和视觉回归，而不是只增加实现代码。
- 不在未获授权时修改现有设计 token 来迎合单个页面。

## 命名与映射

- CSS 建议：`--sop-color-background-page`、`--sop-space-page`、`--sop-radius-control`。
- TypeScript 建议：`tokens.semantic.color.background.page`。
- 组件 prop 使用语义名称，例如 `variant="primary"`、`size="medium"`，不要使用 `color="black"`。
- 状态命名统一使用 `default | hover | active | focusVisible | disabled | loading | error`。

## 允许的推导

Agent 可以：

- 将 token 生成 CSS、Tailwind 或类型安全映射。
- 根据 page pattern 组合已有组件。
- 为具体业务补充文案、数据和权限逻辑。
- 在保持语义的前提下进行响应式重排。

Agent 不可以：

- 将证据文件中的任意 CSS 变量全部复制到项目。
- 将实测页面中的团队名、用户名、资源 ID 或业务文案写入产品。
- 把单张截图中的偶然尺寸当成所有断点的固定要求。
- 绕过 Focus、Disabled、Error 或 Loading 状态以追求截图相似度。
- 在没有更新规范的情况下创造新的圆角、阴影或灰阶。

## 验收清单

- [ ] 使用了语义 token，没有重复硬编码。
- [ ] 页面匹配一个已记录的 page pattern，或说明新增模式。
- [ ] 1280×720 下没有横向溢出，主操作和关键信息在首屏可见。
- [ ] 键盘可完成主要流程，Focus Visible 清晰且不被裁切。
- [ ] Empty、Loading、Error、Disabled 状态已实现。
- [ ] Light 和 Dark theme 均能保持文本、边框和焦点可见性。
- [ ] 长文本、中文和 200% 缩放不会破坏布局。
- [ ] 视觉回归覆盖至少 1280×720 基准状态。
- [ ] 没有引入 Vercel 商标、账号数据或认证信息。

## 证据使用

`evidence/manifest.json` 是设计来源索引。Agent 可以用它核对设计意图，但在新的浏览器采样日期、主题或视口不同的情况下，必须标注差异，不能静默覆盖规范。

