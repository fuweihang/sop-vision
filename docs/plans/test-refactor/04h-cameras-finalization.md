# 任务 04h：Cameras 迁移收尾

> 本任务必须在独立 Codex 会话中执行。04g 通过统一验证入口后才能开始。实施前先阅读
> [任务 4 总说明](./04-frontend-cameras.md)及其中列出的共同限制。

### 任务目标

把 `frontend-cameras` 切换到标准目录的最终命令，补齐 Cameras 路由源码影响规则，并清理全部旧测试
引用，为任务 5 提供稳定的下游 Cameras 验证入口。

### 当前上下文与前置条件

04g 已删除 Cameras 共置业务测试，四层新目录均可运行。Shared、Shell 和 Video 尚未迁移，仍必须
保留各自的旧目录过渡命令；本任务只结束 Cameras 的过渡状态。

### 实施范围

- `test-impact.json` 中 `frontend-cameras` 的 source、tests 和三档最终命令。
- `tests/unit/test_infrastructure/test_test_changed.py` 与
  `test_test_policy_check.py` 的最终状态回归测试。
- Cameras 旧测试路径、空目录和失去用途的 Cameras 专用辅助代码引用。

### 明确不做

不切换 Shared、Shell 或 Video 的最终命令，不迁移它们的测试，不修改生产代码，不再次调整已通过的
Cameras 测试内容。

### 实施步骤

1. 在 `frontend-cameras.source` 中把 `frontend/src/routes/_app/cameras/**` 登记为 integration；保留
   `frontend-shell` 对 `frontend/src/routes/**` 的现有归属，使 Cameras 路由变化同时选择两个模块。
2. 将 Cameras 最终命令固定为：

   ```json
   "commands": {
     "unit": [
       "cd frontend && pnpm exec vitest run tests/unit/cameras"
     ],
     "module": [
       "cd frontend && pnpm exec vitest run tests/unit/cameras tests/component/cameras tests/contract/cameras"
     ],
     "integration": [
       "cd frontend && pnpm exec vitest run tests/unit/cameras tests/component/cameras tests/contract/cameras tests/integration/cameras"
     ]
   }
   ```

3. 更新回归测试，确认四层路径的等级、逐层增加的命令、路由的双模块选择，以及所有命令不再包含
   `src/features/cameras`、`src/mocks/cameras`、`src/routes/_app/cameras` 或旧安全测试路径。
4. 确认 `frontend-video` 的 `impacts: ["frontend-cameras"]` 保持不变，且其 module/integration 选择会
   使用 Cameras 最终命令。
5. 使用 `rg` 检查 Cameras 共置测试、旧路径、重复 Setup 和已废弃 Cameras testing helper。

### 验证方式

只运行 `./scripts/verify-changed.sh`。确认 Test Infrastructure、API Contract、Cameras 以及因路由或配置
变化选中的 Shell/Shared 过渡测试全部通过。

### 完成标准与下一任务衔接

- Cameras 测试只位于 unit、component、contract 和 integration 标准目录。
- 公共生成物检查只位于 `contract/api_contract`，不由 Cameras 命令重复执行。
- Cameras 路由变化会同时执行 Shell 与 Cameras integration。
- Video 变化可以通过既有影响关系执行 Cameras 最终命令。
- Shared、Shell、Video 的旧目录过渡命令继续有效，留给各自任务切换。

任务 4 至此完成，下一任务开始 Frontend Video 测试迁移。

## 导航

- [上一任务：04g React Query、MSW 与路由流程](./04g-cameras-integration.md)
- [返回任务 4](./04-frontend-cameras.md)
- [下一任务：Frontend Video](./05-frontend-video.md)
