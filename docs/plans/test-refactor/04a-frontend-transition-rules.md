# 任务 04a：Frontend 迁移期选择规则

> 本任务必须在独立 Codex 会话中执行。任务 3 通过统一验证入口后才能开始。实施前先阅读
> [任务 4 总说明](./04-frontend-cameras.md)及其中列出的共同限制。

### 任务目标

修正 Frontend 尚未迁移模块的测试命令，为 04b～04g 建立可以逐步加入新目录、同时继续执行剩余
共置测试的过渡状态。

### 当前上下文与前置条件

当前 `frontend-cameras` 正确运行共置测试，但 `frontend-shared`、`frontend-shell` 和
`frontend-video` 已指向尚不存在的 `frontend/tests/...` 目录。Cameras 路由属于 Shell 源码范围，
`vitest.sensitive.config.ts` 属于 Shared 源码范围；不先修正命令，后续迁移会让统一验证入口执行空目录。

### 实施范围

- `test-impact.json` 中四个 Frontend 模块的迁移期命令。
- `tests/unit/test_infrastructure/test_test_changed.py` 中命令、路径、影响模块和等级回归测试。
- `tests/unit/test_infrastructure/test_test_policy_check.py` 中 Frontend 四层标准目录的接受规则。

### 明确不做

不移动任何 Cameras 测试，不创建空测试目录，不修改 Vitest 配置、生产代码或测试辅助代码，不切换
任何 Frontend 模块到最终命令。

### 实施步骤

1. 让 `frontend-shared` 三档命令暂时运行当前 `frontend/src/lib` 测试。
2. 让 `frontend-shell` 三档命令暂时运行当前 `src/components/app-shell`、`page-state`、
   `route-state` 和 `src/routes` 测试。
3. 让 `frontend-video` 三档命令暂时运行当前 `src/features/video` 测试。
4. 将 `frontend-cameras` 三档命令改为迁移期命令：继续运行四组旧路径，同时分别加入 unit、
   component/contract、integration 新目录。新旧路径可以在迁移期间共同作为 Vitest 过滤条件，但
   同一个测试文件只能保留一份。旧目录过滤条件一直保留到 04h，不需要在每次移动文件后改成剩余
   文件清单。
5. 增加回归测试，确认新测试目录按 unit、module、integration 登记。Cameras 路由源码的双模块
   选择规则在 04h 随最终集成测试一起启用，本阶段只保证 Shell 旧命令能够继续运行路由测试。

### 验证方式

只运行 `./scripts/verify-changed.sh`，确认 Test Infrastructure 通过，并由回归测试证明四个 Frontend
模块的过渡命令都指向当前真实存在的测试。

### 完成标准与下一任务衔接

- 尚未迁移模块不再执行空的新目录。
- Cameras 命令能够同时发现新目录与剩余共置测试。
- 标准 Frontend 测试路径已被唯一登记，选择等级正确。

下一任务开始迁移 Cameras 纯规则测试；04b 只能删除自己已经迁移的旧文件和命令片段。

## 导航

- [返回任务 4](./04-frontend-cameras.md)
- [下一任务：04b Cameras Unit 测试](./04b-cameras-unit.md)
