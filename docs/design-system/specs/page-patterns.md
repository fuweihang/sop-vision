# Page Patterns

本文件只定义可复用页面结构和共享状态。具体路由、字段、操作、状态转换和业务流程由对应模块文档、
产品需求或实施计划定义。

## Shared App Shell

```text
TooltipProvider
└─ SidebarProvider
   ├─ Sidebar
   │  ├─ SidebarHeader
   │  ├─ SidebarContent / SidebarMenu
   │  └─ SidebarFooter
   └─ SidebarInset
      ├─ Header
      └─ TanStack Router Outlet
```

- Desktop 使用 Icon-collapsible Sidebar。
- Compact 使用 Sidebar 自带 Sheet。
- Active Route 使用 `isActive`/`data-active`。
- Header 中间显示 Breadcrumb，层级页面可以提供返回操作。

## Resource List

适用于需要搜索、筛选或浏览一组同类资源的页面。

Sections：

1. Page Header：标题、说明和至多一个视觉最强的主操作。
2. 可选的 Search、Filter 和辅助操作。
3. Empty、Card Grid、语义 Table 或其他结构化集合。
4. 集合较大时使用 Pagination 或明确的增量加载方式。

集合使用 Card 还是 Table 由信息密度决定。Card 适合突出单个资源摘要，Table 适合比较重复字段。
具体字段、筛选条件和操作由业务文档定义。

## Resource Detail

适用于展示一个资源及其关联信息的页面。

Sections：

1. Entity Header：名称、说明和当前可用操作。
2. 可选的主要可视区域，例如固定比例媒体或交互画布。
3. 一个或多个 Information Section，使用 Card 组织。
4. 可选的关联资源集合，使用语义 Table、List 或 Card Grid。
5. 业务确有不可逆操作时，使用独立 Destructive Section。

宽屏可以使用 `layout.grid.detail_split` 组合主要可视区域和信息区；低于指定断点后恢复单列阅读顺序。
页面不得因为长标识符、机器可读地址或数据表格产生全局水平滚动。

## Form Dialog

- 使用 Field 系列组件和与值类型匹配的表单控件。
- Dialog 必须包含 Title；需要补充上下文时使用 Description。
- 表单布局使用 `layout.grid.form`，紧凑视口降为单列。
- 提交失败时显示与字段关联的错误，并把焦点移到首个无效字段或错误摘要。
- Footer 保持操作可见；内容过长时只让 Body 滚动。
- 保存期间保持按钮尺寸、阻止重复提交，并提供可感知反馈。

## Destructive Confirmation

所有不可逆操作使用 AlertDialog：

```text
Title
对象和不可逆后果
Cancel
Destructive Confirm
```

不使用普通 Dialog 或 `window.confirm()`。具体确认条件和业务限制由对应模块文档定义。

## Shared States

### Empty

- 使用 Empty。
- 标题说明缺少的具体资源。
- Description 提供原因或下一步。
- 只有用户能够解决时才显示 Action。

### Loading

- 首次加载使用 Skeleton。
- 控件操作使用 Spinner，并保持几何尺寸。
- 固定比例内容在加载期间保持原比例。

### Error

- 页面级错误使用 Alert。
- 表单错误使用 FieldError。
- 异步结果使用 Sonner 或可感知状态区域。
- 提供恢复动作或下一步。

## 内容边界

本文件不得记录：

- 具体路由、资源名称、字段或表格列；
- 某个业务的按钮、枚举、状态机或权限；
- 协议地址、复制规则或数据校验；
- 单一业务专用的操作流程或交互状态。

Design 输出说明所选页面模式、Sections、组件、状态和 Layout Reflow。Coding 输出说明使用的 shadcn
组件；新 primitive 先通过 CLI 添加并更新 `components.yaml`。
