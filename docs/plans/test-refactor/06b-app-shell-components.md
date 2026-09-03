# 任务 06b：App Shell 组件行为

> 本任务必须在独立 Codex 会话中执行。06a 通过统一验证入口后才能开始。实施前先阅读
> [任务 6 总说明](./06-frontend-shared-app-shell.md)及其中列出的共同限制。

### 任务目标

重新评估 App Header、Sidebar、Page State 和 Route State 的组件行为测试，将用户可见状态、交互、
无障碍和已确认的关键布局规则迁入 `frontend/tests/component/app_shell/`。

### 当前上下文与前置条件

06a 已建立 Shell 新旧路径并存的迁移命令。当前相关测试位于：

- `frontend/src/components/app-shell/app-header.test.tsx`
- `frontend/src/components/app-shell/app-sidebar.test.tsx`
- `frontend/src/components/page-state/page-state.test.tsx`
- `frontend/src/components/page-state/query-page-state.test.tsx`
- `frontend/src/components/route-state/route-state.test.tsx`

`route-state.test.tsx` 同时包含可见 Pending 状态和 Router invalidate 协作，后者属于 06c 的路由集成范围，
不能随组件测试一起迁入 component。

### 实施范围

- `frontend/tests/component/app_shell/` 中 Header、Sidebar、Page State、Query Page State 和 Route Pending
  测试。
- 当前五个共置测试文件中与组件行为对应的测试和失去用途的本地辅助代码。
- 与这些测试直接相关的测试名称、Fixture 和断言清理。

### 明确不做

不迁移 `routes/_app/-route-layouts.test.tsx`、Router invalidate 错误恢复、Shared 测试或公共测试工具；
不切换 Shell 最终命令；不修改生产组件、设计系统或响应式断点。

### 实施步骤

1. 逐个测试说明需要防止的缺陷，删除重复覆盖、内部调用次数和没有明确设计依据的 DOM/CSS 实现断言。
2. 迁移 App Header 的 Breadcrumb、返回链接、移动端导航入口、Theme Toggle、截断和合法列表结构。
   只有 `docs/design-system/` 明确要求的固定高度、截断和中心布局规则才保留 class 断言。
3. 迁移 App Sidebar 的移动端关闭、浏览器导航、断点切换、键盘折叠和折叠态 Tooltip 行为。
4. 迁移 Page State 与 Query Page State 的空数据、搜索无结果、首次失败、后台刷新和重试状态。
5. 将 Route Pending 的可访问状态和列表骨架迁入 component；Router invalidate 测试留在旧文件供 06c 处理。
6. 每迁移一组测试就删除旧副本；如果旧文件仍包含 06c 的测试，只保留该测试及必需辅助代码。

### 验证方式

只运行 `./scripts/verify-changed.sh`。确认 Shell 迁移期 module 命令同时覆盖新组件目录和尚未迁移的路由
集成测试，且没有重复执行同一个用例。

### 完成标准与下一任务衔接

- App Shell 用户可见组件行为只存在于 `tests/component/app_shell/`。
- Route State 的 Router invalidate 协作仍明确留给 06c，没有误放进 component。
- 已迁移旧文件和重复辅助代码已删除。
- Shell 迁移期命令和统一验证入口通过。

下一任务迁移完整路由流程并切换 Shell 最终命令。

## 导航

- [上一任务：06a Shared 与 Shell 迁移期选择规则](./06a-shared-shell-transition-rules.md)
- [返回任务 6](./06-frontend-shared-app-shell.md)
- [下一任务：06c App Shell 路由集成与收尾](./06c-app-shell-routing-and-finalization.md)
