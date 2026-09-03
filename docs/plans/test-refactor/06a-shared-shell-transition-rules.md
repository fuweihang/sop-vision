# 任务 06a：Shared 与 Shell 迁移期选择规则

> 本任务必须在独立 Codex 会话中执行。05d 通过统一验证入口后才能开始。实施前先阅读
> [任务 6 总说明](./06-frontend-shared-app-shell.md)及其中列出的共同限制。

### 任务目标

为 Shared 与 Shell 建立旧共置测试和四层标准目录可以同时运行的迁移状态，并提前登记任务 06e 将使用
的公共测试支持路径，使后续每次移动测试都能通过统一验证入口检查。

### 当前上下文与前置条件

Cameras 与 Video 已使用最终命令。`frontend-shared` 仍只运行 `src/lib`，`frontend-shell` 仍只运行
四组源码旁测试。四层测试目录已经登记到模块 `tests` 规则，但测试工具回归仍把 Shared 与 Shell 当作
完全未迁移模块。`frontend/src/test/**` 暂时仍在 `ignored_paths` 中，必须保留到 06e 实际删除旧目录。

### 实施范围

- `test-impact.json` 中 `frontend-shared`、`frontend-shell` 的迁移期命令。
- `frontend-shared.source` 中公共 Setup、browser/media mocks 和 render-router 的最终路径登记。
- `tests/unit/test_infrastructure/test_test_changed.py` 中命令、路径、等级和影响传播回归。
- `tests/unit/test_infrastructure/test_test_policy_check.py` 中 Shared 与 App Shell 标准目录接受规则。

### 明确不做

不移动或修改业务测试、Setup、Mock 或 render-router；不创建空测试目录；不修改 Vitest 配置、生产代码、
Cameras/Video 命令或 `frontend/src/test/**` 的临时豁免；不切换 Shared 或 Shell 到最终命令。

### 实施步骤

1. 将 Shared 三档命令改为以下迁移期状态：

   ```json
   "commands": {
     "unit": [
       "cd frontend && pnpm exec vitest run src/lib tests/unit/shared"
     ],
     "module": [
       "cd frontend && pnpm exec vitest run src/lib tests/unit/shared tests/component/shared tests/contract/shared"
     ],
     "integration": [
       "cd frontend && pnpm exec vitest run src/lib tests/unit/shared tests/component/shared tests/contract/shared tests/integration/shared"
     ]
   }
   ```

2. 将 Shell 三档命令改为以下迁移期状态：

   ```json
   "commands": {
     "unit": [
       "cd frontend && pnpm exec vitest run src/components/app-shell src/components/page-state src/components/route-state src/routes tests/unit/app_shell"
     ],
     "module": [
       "cd frontend && pnpm exec vitest run src/components/app-shell src/components/page-state src/components/route-state src/routes tests/unit/app_shell tests/component/app_shell tests/contract/app_shell"
     ],
     "integration": [
       "cd frontend && pnpm exec vitest run src/components/app-shell src/components/page-state src/components/route-state src/routes tests/unit/app_shell tests/component/app_shell tests/contract/app_shell tests/integration/app_shell"
     ]
   }
   ```

3. 在 `frontend-shared.source` 中精确加入以下路径并设为 integration：
   - `frontend/tests/setup.ts`
   - `frontend/tests/support/browser-mocks.ts`
   - `frontend/tests/support/media-browser-mocks.ts`
   - `frontend/tests/support/render-router.tsx`

   不使用 `frontend/tests/support/**`，避免覆盖 Cameras 和 Video 的专用 Support 规则。
4. 把“Frontend 未迁移模块”回归改成 Shared/Shell 迁移期命令回归，确认 unit、module、integration 逐层
   增加目录且始终保留尚未迁移的旧路径。
5. 增加 Shared/App Shell 四层目录唯一归属与等级测试；增加公共 Setup/Support 路径选择 Shared、Shell、
   Cameras、Video integration 的测试。

### 验证方式

只运行 `./scripts/verify-changed.sh`。确认 Test Infrastructure 通过，回归测试证明新旧路径并存时不会
遗漏当前测试，也不会让公共 Support 失去影响模块。

### 完成标准与下一任务衔接

- Shared 与 Shell 的迁移期命令能运行当前旧测试和后续加入的新目录。
- Shared/App Shell 四层路径有唯一模块和正确等级。
- 公共 Setup/Support 最终路径会选择四个 Frontend 模块的 integration。
- `frontend/src/test/**` 及其临时豁免仍保持不变。

下一任务迁移 App Shell 组件行为测试；06b 只能删除自己已经迁移的旧测试。

## 导航

- [返回任务 6](./06-frontend-shared-app-shell.md)
- [下一任务：06b App Shell 组件行为](./06b-app-shell-components.md)
