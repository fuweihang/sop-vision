# 任务 05d：Stream Session 集成与迁移收尾

> 本任务必须在独立 Codex 会话中执行。05c 通过统一验证入口后才能开始。实施前先阅读
> [任务 5 总说明](./05-frontend-video.md)及其中列出的共同限制。

### 任务目标

迁移 Stream Session 的 React 生命周期测试，把 `frontend-video` 切换到四层标准目录的最终命令，
加入固定 MediaMTX reader 校验，并清理全部 Video 旧测试引用，为任务 6 提供稳定验证入口。

### 当前上下文与前置条件

05a～05c 已迁移 unit、component、contract 和 Video test support。此时只剩
`stream-session-provider.test.tsx` 与 `use-stream-session.test.tsx` 共置测试；Video 命令仍保留
`src/features/video` 过滤条件。公共 Setup、browser/media mocks 和 render-router 尚未迁移，这是任务 6
开始前的预期状态。

### 实施范围

- `frontend/tests/integration/video/` 中的 Provider、Hook 和 Strict Mode 生命周期测试。
- `test-impact.json` 中 `frontend-video` 的最终命令。
- `tests/unit/test_infrastructure/test_test_changed.py` 与
  `test_test_policy_check.py` 的 Video 最终状态回归测试。
- Video 共置测试、旧命令、测试 Fake 旧路径和失去用途的辅助代码引用。

### 明确不做

不移动或修改 Shared、Shell、公共 Setup、browser/media mocks、render-router 或 Vitest 配置；不执行
`whep:test-source`；不新增真实媒体 E2E、视觉测试或生产代码修改。

### 实施步骤

1. 将 Provider 的 Manager 所有权、Strict Mode 紧邻重挂载和真实卸载释放行为迁入
   `integration/video`。
2. 将 `useStreamSession` 对 Context、Manager、React 生命周期、source/URL 切换和空输入的协作行为迁入
   `integration/video`。不要重复 05b 已覆盖的 Manager 内部引用规则。
3. 将 Video 最终命令固定为：

   ```json
   "commands": {
     "unit": [
       "cd frontend && pnpm exec vitest run tests/unit/video"
     ],
     "module": [
       "cd frontend && pnpm exec vitest run tests/unit/video tests/component/video tests/contract/video"
     ],
     "integration": [
       "cd frontend && pnpm exec vitest run tests/unit/video tests/component/video tests/contract/video tests/integration/video",
       "cd frontend && pnpm vendor:check"
     ]
   }
   ```

   `run-whep-test-source.mjs` 继续作为 integration 影响输入，但不作为自动命令启动真实媒体源。
4. 更新回归测试，确认：
   - 四层目录按 unit、module、integration 选择唯一 Video 模块；
   - 三档命令逐层增加目录；
   - integration 包含 `pnpm vendor:check`，unit/module 不包含；
   - 所有命令不再包含 `src/features/video`，也不包含 `whep:test-source`；
   - Video source 变化和 Video support 变化仍按预期触发 Cameras 最终命令；
   - Shared、Shell 的迁移期命令保持不变。
5. 使用 `rg` 检查 `frontend/src/features/video/` 中的 `*.test.ts(x)`、旧
   `features/video/testing/fakes` 导入、重复 Fake、重复 Setup 和 Video 旧命令，删除空目录和失去用途的
   Video 专用辅助代码。

### 验证方式

只运行 `./scripts/verify-changed.sh`。确认 Test Infrastructure、Video 四层测试、reader 固定副本校验和
受影响的 Cameras 最终测试全部通过；不能通过手工缩小范围绕过 integration。

### 完成标准与下一任务衔接

- Video 测试只位于 unit、component、contract 和 integration 标准目录。
- `frontend-video` 最终命令按风险逐层执行，integration 同时运行 `pnpm vendor:check`。
- `FakeStreamSession` 只位于 `tests/support/video`，生产源码中没有 Video 测试辅助代码。
- 公共 Setup、browser/media mocks 和 render-router 仍可供现有测试使用，留给任务 6 统一迁移。
- Video 和 Cameras 最终测试全部通过。

任务 5 至此完成，下一任务开始 Frontend Shared 与 App Shell 测试重构。

## 导航

- [上一任务：05c Video 组件行为](./05c-video-components.md)
- [返回任务 5](./05-frontend-video.md)
- [下一任务：Frontend Shared 与 App Shell](./06-frontend-shared-app-shell.md)
