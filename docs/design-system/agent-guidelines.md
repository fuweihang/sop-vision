# Agent Guidelines

## 开始前

1. 读取 `catalog.json`、本文件和任务相关规格。
2. 检查现有 `frontend/src/components/ui/`，确认能否直接组合。
3. 在 `page-patterns.md` 中选择页面模式。
4. 冲突按 `catalog.json#sourceOfTruthOrder` 处理。

## Design

- 先定义信息层级、页面模式和状态，再处理视觉细节。
- 沿用原型的 Shell、Cameras/Tasks 信息结构和响应式意图。
- 使用 Foundations 的中性、紧凑、工程工具化原则。
- 输出覆盖 Catalog Baseline、窄屏降级、Empty、Loading、Error 和 Disabled。
- 不复制历史参考中的商标、账号数据或产品身份。

## Coding

### 组件

- 使用 `frontend/src/components/ui/`，不在页面中重写同名 primitive。
- 缺少组件时使用 shadcn CLI：

  ```bash
  pnpm exec shadcn add <component> --dry-run
  pnpm exec shadcn add <component> --diff <existing-file>
  pnpm exec shadcn add <component>
  ```

- 未经明确确认不得使用 `--overwrite`。
- 保留 Base UI、`data-slot`、`cva` 和 `cn()` 模式。
- 图标使用 Hugeicons，不手写等价 SVG。
- 页面级调整使用现有 variant、size 和局部 `className`。

### Shell 与路由

- Shell 使用 SidebarProvider 组合，移动端沿用 Sidebar 的 Sheet。
- 折叠菜单项提供 Tooltip，并在应用根节点挂载 TooltipProvider。
- 路由使用 TanStack Router；具体路由由 Page Patterns 定义。
- 不复制原型的 Sidebar 状态或 Hash Router。

### 表单与反馈

- 表单使用 Field 系列组件和对应 Base UI 控件。
- 创建/编辑使用 Dialog；不可逆确认使用 AlertDialog。
- 异步操作保留控件尺寸，显示 Loading，并提供可感知反馈。
- 数据列表优先使用语义 Table；响应式变体不得丢失字段名称。

## 可以

- 组合现有组件实现页面模式。
- 添加业务组合组件和局部布局 class。
- 为严格类型、Lint 或可访问性做最小组件调整。
- 在改变项目级决策时同步本目录。

## 不可以

- 从原型复制手写 primitive。
- 直接复制其他工作区组件替代 CLI。
- 绕过 Base UI 的键盘、焦点和 ARIA 行为。
- 为单一页面修改全局主题或组件 API。
- 在多个规格中重复维护相同数值。

## 验收

- [ ] 使用现有 shadcn 组件，没有重复 primitive。
- [ ] 页面符合 Page Patterns，布局符合 Layout。
- [ ] 键盘、Focus、Empty、Loading、Error、Disabled 已覆盖。
- [ ] Light/Dark、Catalog Baseline 和 Reflow 已验证。
- [ ] Tooltip、Dialog、AlertDialog、Toast Provider 按需接入。
- [ ] 格式检查、Lint、测试和生产构建通过。
