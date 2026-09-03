# 任务 06e：公共 Setup、Mock 与 Router 测试工具

> 本任务必须在独立 Codex 会话中执行。06d 通过统一验证入口后才能开始。实施前先阅读
> [任务 6 总说明](./06-frontend-shared-app-shell.md)及其中列出的共同限制。

### 任务目标

将全局 Vitest Setup、浏览器/媒体 Mock 和 Router 渲染工具移到标准测试支持目录，更新所有使用方和
Vitest 配置，并删除 `frontend/src/test/` 及其临时配置豁免。

### 当前上下文与前置条件

Shared、Shell、Cameras 和 Video 已全部使用标准目录及最终命令，但仍从 `@/test/*` 使用
`frontend/src/test/` 下的公共工具。06a 已将这些工具的最终路径精确登记为 `frontend-shared`
integration 输入。Cameras 与 Video 专用 Support 已分别登记给自身模块，不能被 Shared 的通配规则覆盖。

### 实施范围

- `frontend/tests/setup.ts`。
- `frontend/tests/support/browser-mocks.ts`。
- `frontend/tests/support/media-browser-mocks.ts`。
- `frontend/tests/support/render-router.tsx`。
- Shared、Shell、Cameras、Video 测试中的公共工具导入。
- `frontend/vitest.config.ts` 的 Setup、测试发现和 coverage 排除配置。
- `frontend/vitest.sensitive.config.ts` 在基础配置增加 `include` 后的精确文件覆盖方式。
- `test-impact.json` 中 `frontend/src/test/**` 的旧 `ignored_paths` 项。
- 测试工具中公共 Support 选择和旧路径拒绝回归。

### 明确不做

不移动 `frontend/src/mocks/` 中仍服务开发环境的 MSW 文件；不修改 Query Client、Router、Provider、
Cameras 或 Video 生产行为；不重新设计已通过的业务测试；不增加测试专用生产 alias、E2E 或视觉测试。

### 实施步骤

1. 按以下目标移动文件，不保留兼容转发文件：

   ```text
   frontend/src/test/setup.ts               -> frontend/tests/setup.ts
   frontend/src/test/browser-mocks.ts       -> frontend/tests/support/browser-mocks.ts
   frontend/src/test/media-browser-mocks.ts -> frontend/tests/support/media-browser-mocks.ts
   frontend/src/test/render-router.tsx      -> frontend/tests/support/render-router.tsx
   ```

2. 更新 Setup 内部导入和所有 Shell、Cameras、Video 测试导入。测试工具使用相对于
   `frontend/tests/` 的路径，不把测试目录加入生产 `@/` alias。
3. 保持 render-router 使用 `tests/support/video/fake-stream-session.ts`，并确认它仍只创建测试用
   Query/Router/Stream Session 环境，不把测试依赖带入生产入口。
4. 更新 `vitest.config.ts`：
   - `setupFiles` 改为 `./tests/setup.ts`。
   - 默认测试发现限制为 `tests/**/*.test.{ts,tsx}`。
   - coverage 继续只统计 `src/**/*.{ts,tsx}`，删除已经失效的 `src/test/**` 排除；在源码旁测试全部删除后，
     同时删除不再需要的 `src/**/*.test.{ts,tsx}` 排除。
5. 同步调整 `vitest.sensitive.config.ts`，确保专项 `test.include` **替换**基础配置的全量 `include`，不能让
   `mergeConfig` 的数组拼接把所有测试加入敏感数据专项；保留 06d 确定的精确文件清单。
6. 删除 `frontend/src/test/`，并从 `test-impact.json.ignored_paths` 删除 `frontend/src/test/**`。不保留旧目录
   豁免，避免后续重新加入源码旁测试时静默跳过选择检查。
7. 更新测试工具回归，确认：
   - 四个公共文件都会选择 Shared、Shell、Cameras、Video integration。
   - Cameras/Video 专用 Support 仍只按自身既有规则选择。
   - 重新出现且实际存在的 `frontend/src/test/*` 不再被忽略，会作为未登记路径失败。
8. 使用 `rg` 检查 `@/test/`、`frontend/src/test`、旧 Setup 路径、重复 browser/media mocks 和重复
   render-router，删除空目录与无用导入。

### 验证方式

只运行 `./scripts/verify-changed.sh`。本任务预期执行 Test Infrastructure 以及 Shared、Shell、Cameras、
Video integration；`vitest.sensitive.config.ts` 的变化还应选择 API Contract，并确认
`pnpm test:sensitive-data` 只执行专项配置列出的文件。不得通过手工缩小范围绕过公共工具的全部使用方。

### 完成标准与下一任务衔接

- 全局 Setup 和公共 Support 只位于 `frontend/tests/`。
- Vitest 默认只发现标准测试目录，并从新 Setup 路径启动。
- 所有 Frontend 测试不再导入 `@/test/*`，不存在重复公共 Mock 或 Router Helper。
- `frontend/src/test/`、coverage 旧排除和影响规则旧豁免全部删除。
- 公共 Support 变化会执行四个 Frontend 模块的 integration，统一验证入口通过。

任务 6 至此完成，下一任务在完整标准目录上检查跨端契约和迁移结果。

## 导航

- [上一任务：06d Shared 规则、HTTP 边界与收尾](./06d-shared-rules-contract-and-finalization.md)
- [返回任务 6](./06-frontend-shared-app-shell.md)
- [下一任务：跨端契约与迁移验收](./07-cross-platform-contract-and-acceptance.md)
