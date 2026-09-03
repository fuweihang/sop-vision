# 任务 6：Frontend Shared 与 App Shell 测试重构

> 本任务规模较大，已拆成 06a～06e 五个顺序任务。每个子任务必须在独立 Codex 会话中执行，
> 前一项通过统一验证入口后才能开始下一项，禁止并行修改同一工作区。

### 任务目标

重新评估 Frontend 公共逻辑、应用外壳、页面状态和路由测试，将它们迁入标准目录；最后把全局
Vitest Setup、浏览器 Mock 和 Router 渲染工具移出生产源码目录，并保证公共测试基础变化会验证所有
Frontend 使用方。

### 当前上下文与前置条件

任务 4 和任务 5（05a～05d）已经完成，Cameras 与 Video 测试及命令均使用标准目录。当前仍有 10 个
Shared/Shell 共置测试文件，分布在 `frontend/src/lib/`、`components/app-shell/`、
`components/page-state/`、`components/route-state/` 和 `routes/`。全局 Setup、browser/media mocks 与
render-router 仍位于 `frontend/src/test/`，同时被 Shell、Cameras 和 Video 使用。

开始每个子任务前，都要重新读取当前版本的 `AGENTS.md`、总计划、`test-policy`、Frontend 参考、
`test-impact.json` 和该子任务方案。判断测试是否低价值或易碎时，读取 `test-smells.md`。修改 App Shell
或页面状态测试前，还要读取与断言内容直接相关的 `docs/design-system/` 规则。

### 已确定的测试归属

- Route Meta、Sidebar Preference 和 Problem 字段路径映射等确定性规则进入
  `frontend/tests/unit/shared/`。
- Axios Client 脱敏以及 Problem 媒体类型、Schema、HTTP status、trace 一致性进入
  `frontend/tests/contract/shared/`。
- App Header、App Sidebar、Page State、Query Page State、Route Pending 等可见状态和交互进入
  `frontend/tests/component/app_shell/`。
- 路由重定向、响应式 Shell、页面切换焦点、Skip Link、子路由错误恢复和 Not Found 进入
  `frontend/tests/integration/app_shell/`。
- 当前没有需要机械补齐的 Shared component/integration 或 App Shell unit/contract 测试；没有明确风险时
  不创建空目录或占位测试。

### 已确定的影响规则

- Shared 和 Shell 在迁移期间都使用新旧路径并存的命令；只有各自收尾任务可以删除旧路径。
- `api-client.ts`、`api-errors.ts` 的变化至少执行 Shared module，以覆盖对应 contract 测试。
- `App.tsx`、`routes/**` 和 `routeTree.gen.ts` 的变化执行 Shell integration；普通 Shell 组件源码变化执行
  module。
- 迁移后的 `frontend/tests/setup.ts`、browser/media mocks 和 render-router 精确登记为
  `frontend-shared` integration 输入，再通过既有 `impacts` 验证 Shell、Cameras 和 Video。
- `vitest.sensitive.config.ts` 同时登记给 `api-contract`，配置变化继续由现有敏感数据脚本验证，不在
  Shared 命令中复制专项检查。
- 不把整个 `frontend/tests/support/**` 登记给 Shared；Cameras 和 Video 专用 Support 继续由各自模块
  单独负责，避免无关改动运行全部 Frontend 测试。

### 所有子任务共同限制

1. 五个子任务必须严格按 06a～06e 串行执行。
2. 每个阶段先说明测试要防止的缺陷，再决定保留、合并、拆分、重写或删除，不按旧文件机械搬运。
3. 已迁移测试立即删除旧副本；迁移期命令可以保留旧目录过滤条件，但同一个测试文件只能存在一份。
4. 不修改生产代码行为，不重做 Cameras 或 Video 测试，不移动仍服务开发环境的 `frontend/src/mocks/`。
5. 不新增 E2E、视觉回归、截图、快照或新的通用测试框架。
6. 每个阶段交付前只运行 `./scripts/verify-changed.sh`；失败时按脚本日志路径使用 `rg` 定位。
7. 只有 06e 可以删除 `frontend/src/test/`，并必须同时清理 Vitest 与影响规则中的旧路径。

### 子任务执行顺序

1. [06a：Shared 与 Shell 迁移期选择规则](./06a-shared-shell-transition-rules.md)
2. [06b：App Shell 组件行为](./06b-app-shell-components.md)
3. [06c：App Shell 路由集成与收尾](./06c-app-shell-routing-and-finalization.md)
4. [06d：Shared 规则、HTTP 边界与收尾](./06d-shared-rules-contract-and-finalization.md)
5. [06e：公共 Setup、Mock 与 Router 测试工具](./06e-frontend-test-support.md)

### 任务 6 完成标准与下一任务衔接

- Shared 与 App Shell 测试只位于标准测试目录，并按风险使用最低有效层级。
- Shared 与 Shell 最终命令按 unit、module、integration 逐层增加标准目录，不再引用共置测试。
- 公共 Setup 和 Support 位于 `frontend/tests/`，所有 Frontend 模块使用同一份实现。
- 公共测试基础变化会执行 Shared、Shell、Cameras 和 Video integration。
- `frontend/src/test/`、对应 Vitest 旧配置和 `test-impact.json` 旧豁免已经删除。
- 统一验证入口通过。

任务 6 至此完成，下一任务检查跨端契约、敏感数据和全部测试路径的最终归属。

## 导航

- [上一任务：05d Stream Session 集成与迁移收尾](./05d-video-integration-and-finalization.md)
- [返回总计划](./README.md)
- [首先执行：06a Shared 与 Shell 迁移期选择规则](./06a-shared-shell-transition-rules.md)
- [任务 6 完成后：跨端契约与迁移验收](./07-cross-platform-contract-and-acceptance.md)
