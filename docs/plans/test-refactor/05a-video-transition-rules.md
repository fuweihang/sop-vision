# 任务 05a：Video 迁移期选择规则

> 本任务必须在独立 Codex 会话中执行。04h 通过统一验证入口后才能开始。实施前先阅读
> [任务 5 总说明](./05-frontend-video.md)及其中列出的共同限制。

### 任务目标

为 Video 建立旧共置测试和四层新目录可以同时运行的迁移状态，并提前登记 Video Session Fake 的
最终支持目录，避免后续移动测试时统一验证入口遗漏新文件。

### 当前上下文与前置条件

Cameras 已切换到标准目录的最终命令。`frontend-video` 的 tests 规则已经登记四层新目录，但三档命令
仍只运行 `src/features/video`；测试工具回归测试也把 Video 当作完全未迁移模块。Shared 和 Shell
仍处于旧目录状态，不能在本任务中切换。

### 实施范围

- `test-impact.json` 中 `frontend-video` 的迁移期命令和 `frontend/tests/support/video/**` source 规则。
- `tests/unit/test_infrastructure/test_test_changed.py` 中 Video 命令、目录层级、支持代码和影响传播测试。
- `tests/unit/test_infrastructure/test_test_policy_check.py` 中 Video 四层标准目录的接受测试。

### 明确不做

不移动或修改任何 Video 测试、Fake、Setup、browser/media mocks、render helper 或生产代码；不创建空测试
目录；不切换 Shared、Shell 或 Video 到最终命令。

### 实施步骤

1. 在 `frontend-video.source` 中加入：

   ```json
   {"paths": ["frontend/tests/support/video/**"], "level": "integration"}
   ```

   Support 改动必须执行 Video integration，并通过既有 `impacts` 执行 Cameras integration，才能覆盖
   当前所有 Fake 使用方。
2. 将 Video 三档命令改为迁移期命令：

   ```json
   "commands": {
     "unit": [
       "cd frontend && pnpm exec vitest run src/features/video tests/unit/video"
     ],
     "module": [
       "cd frontend && pnpm exec vitest run src/features/video tests/unit/video tests/component/video tests/contract/video"
     ],
     "integration": [
       "cd frontend && pnpm exec vitest run src/features/video tests/unit/video tests/component/video tests/contract/video tests/integration/video"
     ]
   }
   ```

   旧目录过滤条件保留到 05d；同一个测试文件只能存在一份。
3. 把“Frontend 未迁移模块”回归测试缩小到 Shared 和 Shell，单独增加 Video 迁移期命令测试。
4. 增加 Video 四层目录唯一归属和等级测试：unit 对应 unit，component/contract 对应 module，
   integration 对应 integration。
5. 增加 Support 变化选择 Video、Cameras integration 的测试，并保留普通 Video 生产文件变化向 Cameras
   传播的现有检查。

### 验证方式

只运行 `./scripts/verify-changed.sh`，确认 Test Infrastructure 通过。回归测试必须证明迁移期命令既能
执行当前共置测试，也能发现后续加入的新目录。

### 完成标准与下一任务衔接

- Video 新旧路径并存的三档命令可用。
- Video 四层目录和专用 Support 均有明确选择等级。
- Shared、Shell 和 Cameras 命令保持当前有效状态。

下一任务开始迁移确定性规则、WHEP 契约和 Session Fake。

## 导航

- [返回任务 5](./05-frontend-video.md)
- [下一任务：05b 确定性规则、WHEP 契约与 Session Fake](./05b-video-rules-contract-and-support.md)
