# Interaction and Accessibility

冲突顺序由 `catalog.json#sourceOfTruthOrder` 定义。Base UI 负责 primitive 的基础键盘行为、ARIA 状态和焦点管理。

## 状态

| 状态          | 要求                                  |
| ------------- | ------------------------------------- |
| Default       | 关键操作不能依赖 Hover 才出现         |
| Hover         | 使用组件既有反馈，不引发布局变化      |
| Active        | 沿用组件反馈，不使用缩放              |
| Focus Visible | 使用组件 Ring，且不得被裁切           |
| Disabled      | 阻止操作；重要数据仍可读              |
| Loading       | 保持组件尺寸、声明 Busy、防止重复提交 |
| Error         | 使用 `aria-invalid` 并提供可修复文本  |
| Selected/Open | 使用 primitive 的状态属性和语义表面   |

## Primitive 责任

- 不重复实现 Focus Trap、方向键导航、Switch 或 Listbox 状态机。
- 不覆盖 primitive 默认行为，除非有明确项目需求和对应测试。
- 原型中的焦点循环、原生 Select 和手写 ARIA Switch 不进入 React 实现。

## 键盘与焦点

- 所有交互元素通过 Tab 到达，顺序与阅读顺序一致。
- Enter/Space、Escape 和方向键行为沿用对应 primitive。
- Sidebar 支持组件定义的键盘快捷键。
- 不允许正数 `tabindex`。
- 路由完成后，将焦点放到主标题或主内容起点。
- Active Menu 不能只改变图标颜色。
- 可点击 Card 使用语义 Link/Button 并提供独立 Focus Visible。

## 文本、颜色与目标区域

- 正文和关键控件文字目标对比度至少 4.5:1。
- 大字号和非关键视觉至少 3:1。
- 焦点、轮廓和图标相对相邻颜色至少 3:1。
- 状态色必须配合文本、图标或形状。
- 点击区域遵循组件实现；Touch 场景可通过外层 Hit Area 扩展。
- 相邻 Destructive 与 Confirm 操作保持清晰间隔。

## 表单

- 使用 Field、Label、Description 和 Error 组合。
- Placeholder 不能替代 Label。
- 帮助文本和错误文本必须与控件关联。
- 错误说明如何修复。
- 重要 Disabled 数据应改用 Readonly 或独立文本展示。
- 保存结果通过 Sonner 或 `aria-live` 区域反馈。

## Floating Surfaces

- 创建和编辑使用 Dialog；不可逆确认使用 AlertDialog。
- Focus、Escape、Outside Interaction 和 Focus Restore 由 Base UI 管理。
- Dialog 必须有 Title；需要补充上下文时使用 Description。
- 复杂表单可以扩展 Content，但必须保留视口边距和内部滚动。
- Mobile Sidebar 使用 Sidebar 自带的 Sheet。
- 折叠菜单项使用 Tooltip，应用根节点挂载 TooltipProvider。
- 关闭的移动 Sidebar 不得继续参与 Tab 顺序。

## Reflow 与 Motion

- Reflow 目标、断点和局部滚动例外由 `layout.yaml` 定义。
- 不为根元素、Shell 或主内容设置固定最小宽度。
- 动效只解释状态变化。
- Reduced Motion 下移除非必要位移、缩放和动画。
- Skeleton 匹配最终内容几何，避免强烈闪烁。

## 验证

自动检查：

- 语义结构、名称、Tab、`aria-invalid`。
- Dialog/AlertDialog Focus 行为。
- Light/Dark、Reduced Motion、Lint、测试和构建。

人工检查：

- Focus Ring、中文和长文本。
- Catalog Baseline 与 Layout Reflow 目标。
- 完整键盘流程。
- Sidebar Tooltip 和 Mobile Sheet。
