# 任务 06c：App Shell 路由集成与收尾

> 本任务必须在独立 Codex 会话中执行。06b 通过统一验证入口后才能开始。实施前先阅读
> [任务 6 总说明](./06-frontend-shared-app-shell.md)及其中列出的共同限制。

### 任务目标

迁移 App Shell 的路由、焦点和错误恢复流程，修正路由源码的验证等级，并把 `frontend-shell` 切换到
只运行标准目录的最终命令。

### 当前上下文与前置条件

06b 已迁移组件行为。此时路由布局测试仍位于
`frontend/src/routes/_app/-route-layouts.test.tsx`，Route Error 的 Router invalidate 测试可能暂留在
`frontend/src/components/route-state/route-state.test.tsx`。公共 render-router 和 browser mocks 仍位于
`frontend/src/test/`，这是 06e 前的预期状态。

当前 `frontend-shell.source` 把全部 Shell 和路由源码统一设为 module。如果不拆开规则，Tasks 等普通
路由变化不会执行新的 integration 测试。

### 实施范围

- `frontend/tests/integration/app_shell/` 中路由布局、导航、焦点和错误恢复测试。
- `frontend-shell.source` 中组件与路由源码等级。
- `frontend-shell.commands` 的最终三档命令。
- 测试工具中的 Shell 最终路径、命令和源码选择回归。
- Shell 共置测试、旧命令和失去用途的本地辅助代码。

### 明确不做

不移动公共 Setup、browser/media mocks 或 render-router；不迁移 Shared 测试；不修改 Cameras/Video 测试
设计或生产路由行为；不新增浏览器 E2E。

### 实施步骤

1. 将根路径重定向、Shell 路由布局、767/768 响应式边界、页面切换焦点、Skip Link、子路由失败时保留
   Shell、Router invalidate 重试和 Not Found 迁入 integration。
2. 合并 06b 留下的 Route Error Router invalidate 测试，避免 component 与 integration 重复覆盖同一行为。
3. 拆分 `frontend-shell.source`：
   - App Shell、Layout、Page State、Route State 组件及品牌资源保持 module。
   - `frontend/src/App.tsx`、`frontend/src/routes/**`、`frontend/src/routeTree.gen.ts` 设为 integration。
   - 保留 Cameras 路由同时属于 `frontend-cameras` integration 的既有规则。
4. 将 Shell 最终命令固定为：

   ```json
   "commands": {
     "unit": [
       "cd frontend && pnpm exec vitest run tests/unit/app_shell"
     ],
     "module": [
       "cd frontend && pnpm exec vitest run tests/unit/app_shell tests/component/app_shell tests/contract/app_shell"
     ],
     "integration": [
       "cd frontend && pnpm exec vitest run tests/unit/app_shell tests/component/app_shell tests/contract/app_shell tests/integration/app_shell"
     ]
   }
   ```

5. 更新回归测试，确认三档命令逐层增加标准目录且不再包含四组旧路径；普通路由选择 Shell integration，
   Cameras 路由继续同时选择 Shell 与 Cameras integration。
6. 使用 `rg` 检查 Shell、Page State、Route State 和 routes 下的共置测试与旧命令，删除空目录和失去用途
   的测试辅助代码。

### 验证方式

只运行 `./scripts/verify-changed.sh`。确认 Test Infrastructure、Shell component/integration 以及因 Cameras
路由双重归属而选择的最终 Cameras 测试全部通过。

### 完成标准与下一任务衔接

- App Shell 测试只位于标准 component 和 integration 目录。
- 路由源码变化会执行 Shell integration，普通组件变化执行 module。
- Shell 最终命令不再包含源码旁测试路径。
- 公共测试工具仍位于旧位置并可正常使用，留给 06e 一次迁移。

下一任务迁移 Shared 纯规则和 HTTP 边界测试。

## 导航

- [上一任务：06b App Shell 组件行为](./06b-app-shell-components.md)
- [返回任务 6](./06-frontend-shared-app-shell.md)
- [下一任务：06d Shared 规则、HTTP 边界与收尾](./06d-shared-rules-contract-and-finalization.md)
