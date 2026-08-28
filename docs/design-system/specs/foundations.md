# Foundations

## 设计方向

SOP Vision 使用 shadcn/ui `base-nova` 的中性、紧凑、工程工具化视觉语言。页面优先表达资源、
状态、关系和操作层级。

冲突顺序由 `catalog.json#sourceOfTruthOrder` 定义。

## 核心原则

1. **组件基线来自 shadcn。** Primitive geometry、variant 和状态以运行时组件源码为准。
2. **原型只定义布局意图。** Shell、页面结构、业务流程和响应式方向可沿用，手写 primitive 不可移植。
3. **层级来自语义表面。** 使用 shadcn 的 Background、Card、Popover、Muted、Accent、Border 和 Ring。
4. **保持紧凑密度。** 使用 Layout Token 和组件默认 size，不为匹配截图创造局部尺寸。
5. **主次操作明确。** 页面只设置一个视觉最强的主操作，其他操作使用现有 variant。
6. **状态不只依赖颜色。** 同时使用文字、图标、形状、透明度或位置反馈。
7. **运行时优先。** Design System 记录项目决策，不建立平行组件库或主题。

## 颜色

- 页面、Card、Popover、Primary、Secondary、Muted、Accent、Destructive、Border、Input、Ring 和 Sidebar 使用运行时 shadcn CSS Variables。
- 业务组件使用 Tailwind 语义类，不直接选择原始色阶。
- 状态颜色必须配合文本、Icon、Badge 或结构标记。
- 成功和警告等新增业务语义必须先进入运行时主题，再登记到主题快照。

精确 Light/Dark 值见 `tokens/runtime-theme.tokens.json`；该文件不能覆盖 `frontend/src/index.css`。

## 排版

- 正文、控件、辅助文本、标题分别使用既有语义层级，不为单个页面创建新字号。
- 页面只保留一个主标题层级；Card 和 Dialog 标题低于页面标题。
- 使用 Geist Variable 和系统 sans-serif 回退。
- ID、参数、时间戳和机器可读地址使用系统等宽字体。
- Muted 文本不承载关键错误、权限、结果或告警。

## 间距、尺寸与圆角

- 使用 `tokens/layout.tokens.json` 中的 spacing、control、radius 和 shell token。
- 页面布局可以选择组件已有 size，但不得重写 primitive 默认尺寸表。
- Card、Dialog、Button、Input、Menu Item 等使用各自组件圆角，不强制统一圆角。
- 长文本、中文、ID 和机器可读地址优先换行，不扩大页面最小宽度。

## 表面与阴影

- 普通 Card 使用语义表面和细 Ring，不额外增加 elevation。
- Floating Content 沿用组件自带 Shadow、Ring 和 Overlay。
- Focus 样式沿用组件实现，业务容器不得裁切。
- 原型 Shadow 只表达层级意图，不覆盖 shadcn 默认值。

## 图标

- 图标库固定为 Hugeicons。
- 使用组件和 Layout Token 定义的 icon size。
- 同一上下文保持一致的描边风格。
- Icon-only Button 必须有可访问名称。
- Hugeicons 有等价图标时不得手写 SVG。

## 边界

- Layout、Card Grid、Table、Preview、交互画布和表单排列可以按页面需要组合。
- Primitive 的内部状态、键盘行为和 ARIA 由 Base UI 管理。
- 页面通过 composition、variant、size 和局部 class 扩展，不创建同名替代组件。
