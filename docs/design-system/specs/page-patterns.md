# Page Patterns

本文件拥有路由和业务页面的目标组合；Shell、Grid 和 Breakpoint 只在 `layout.yaml` 定义。
Shared App Shell 已实现，其余 Cameras/Tasks sections 仍是后续业务实现约束。

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
- Header 中间显示 Breadcrumb，详情页提供返回操作。

## `/cameras`

模式：Camera Resource List。

Sections：

1. 页面标题与说明。
2. Search 和添加 Camera 主操作。
3. Empty 或 `layout.grid.camera_cards`。

Card 展示名称、状态、连接摘要和默认 Source，整体进入 Camera Detail。Empty 说明缺少的资源和下一步。

## `/cameras/$cameraId`

模式：Camera Detail。

Sections：

1. Entity Header：名称、状态、Preview 和编辑。
2. AspectRatio Preview。
3. Connection Information。
4. Camera Sources。
5. Destructive Section。

Source 选择使用 RadioGroup 或 Select；编辑使用 Dialog；删除使用 AlertDialog。机器 ID 和流地址使用等宽字体并可换行、复制。

## `/tasks`

模式：Detection Task Resource List。

Sections：

1. 页面标题与说明。
2. Search 和创建 Task 主操作。
3. Empty 或语义 Table。

Table 展示任务名称、Camera Source、Algorithm、状态和详情操作。Compact 行为使用 `layout.responsive.compact.task_list`。

## `/tasks/$taskId`

模式：Detection Task Detail。

Sections：

1. Entity Header：状态、启停、重载、重启和编辑。
2. AspectRatio Preview、Detection Overlay 和 ROI。
3. ROI Display Switch 与 Legend。
4. Task Information。
5. Algorithm Parameters。
6. Destructive Section。

异步操作显示 Loading 并提供 Sonner 反馈；编辑使用 Dialog；删除使用 AlertDialog。

## Camera Form Dialog

- 使用 Field、Input 和 Button。
- 支持 Create/Edit。
- Source 行可以增删，Icon Button 必须有可访问名称。
- 提交失败聚焦首个无效字段。
- Footer 保持可见，Body 可以滚动。

## Task Form Dialog

- 使用 Field、Input、Textarea、Select、Button 和 Spinner。
- Algorithm 参数按 schema 选择对应 Base UI 控件。
- 表单布局引用 `layout.grid.form`。
- ROI 区域引用 `layout.grid.roi`。

ROI MVP：

- 定义来自 Algorithm API。
- 点选添加顶点，至少三个点完成。
- 重绘只在完成后替换保存值。
- 取消保留保存值，Undo 只影响草稿。
- 不支持顶点拖拽和键盘几何输入。

## Destructive Confirmation

所有不可逆删除使用 AlertDialog：

```text
Title
对象和不可逆后果
Cancel
Destructive Confirm
```

不使用普通 Dialog 或 `window.confirm()`。

## Shared States

### Empty

- 使用 Empty。
- 标题说明缺少的具体资源。
- Description 提供原因或下一步。
- 只有用户能够解决时才显示 Action。

### Loading

- 首次加载使用 Skeleton。
- 控件操作使用 Spinner，并保持几何尺寸。
- Preview 状态保持 AspectRatio。

### Error

- 页面级错误使用 Alert。
- 表单错误使用 FieldError。
- 异步结果使用 Sonner 或可感知状态区域。
- 提供恢复动作或下一步。

## 输出要求

Design 输出：路由、模式、Sections、组件、状态、Catalog Baseline 行为和 Layout Reflow。

Coding 输出：说明使用的 shadcn 组件；新 primitive 先通过 CLI 添加并更新 `components.yaml`。
