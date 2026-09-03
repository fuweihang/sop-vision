# 任务 6：Frontend Shared 与 App Shell 测试重构

> 本任务在独立 Codex 会话中执行。实施前先阅读[总计划与通用要求](./README.md)，完成并通过统一验证入口后再进入下一任务。

### 任务目标

重构 Frontend 公共逻辑、应用外壳、页面状态和路由测试，并把 Vitest Setup 与公共渲染工具迁移到
标准支持目录。

### 当前上下文与前置条件

现有测试分布在 `frontend/src/lib/`、`components/app-shell/`、`components/page-state/`、
`components/route-state/`、`routes/` 和 `frontend/src/test/`。新目录使用
`frontend/tests/<layer>/shared/` 与 `frontend/tests/<layer>/app_shell/`。任务 4 和任务 5 必须完成；
Shared 的影响传播会触发 Shell、Cameras 和 Video。

### 实施范围

- API Client 基础、API errors、route meta、sidebar preference 等共享逻辑。
- App Header、Sidebar、Page State、Route State 和路由布局测试。
- `frontend/tests/setup.ts`、`frontend/tests/support/`。
- Vitest 中与 Setup 和测试发现路径有关的最小配置修改。
- Shared 与 App Shell 对应的 unit、component、contract 和 integration 目录。

### 明确不做

不再次修改 Cameras 或 Video 测试设计，不重构生产组件或路由，不新增视觉或路由 E2E。

### 实施步骤

1. 先迁移 App Shell，区分纯导航规则、组件行为和路由集成流程。
2. 迁移 Shared 纯逻辑、API Client 行为和公共错误处理测试。
3. 将全局 Setup、browser mocks 和 render helper 迁移到 `frontend/tests/setup.ts` 与 `support/`。
4. 更新 Vitest 配置及所有公共辅助代码导入路径。
5. 删除 `frontend/src/test/` 和本任务范围内的共置测试，确认没有重复 Setup。

### 验证方式

运行 `./scripts/verify-changed.sh`。该步骤预期会验证 Shared、App Shell、Cameras 和 Video，不要手工
绕开下游模块。

### 完成标准与下一任务衔接

Frontend 公共 Setup 和 Support 不再位于生产源码目录；Shared、Shell、Cameras 和 Video 使用同一
套测试基础并全部通过。最后一个任务将在完整新目录上检查跨端契约和影响选择。

## 导航

- [返回总计划](./README.md)
- [下一任务](./07-cross-platform-contract-and-acceptance.md)
