# 任务 06d：Shared 规则、HTTP 边界与收尾

> 本任务必须在独立 Codex 会话中执行。06c 通过统一验证入口后才能开始。实施前先阅读
> [任务 6 总说明](./06-frontend-shared-app-shell.md)及其中列出的共同限制。

### 任务目标

把 Shared 确定性规则和公共 HTTP Client 边界放入正确层级，更新敏感数据专项测试路径，并将
`frontend-shared` 切换到只运行标准目录的最终命令。

### 当前上下文与前置条件

Shell 已使用最终命令。Shared 仍处于 `src/lib` 与标准目录并存的迁移状态，现有四个测试文件为
`api-client.test.ts`、`api-errors.test.ts`、`route-meta.test.ts` 和 `sidebar-preference.test.ts`。
`api-errors.test.ts` 同时包含 HTTP Problem 契约和字段路径纯规则，必须按风险拆开，不能整文件归入一个
层级。`vitest.sensitive.config.ts` 仍引用两个旧 Shared 测试路径。

### 实施范围

- `frontend/tests/unit/shared/` 中 Route Meta、Sidebar Preference 和 Problem 字段路径规则。
- `frontend/tests/contract/shared/` 中 Axios Client 脱敏和 Problem 响应识别。
- `frontend-shared.source` 中 API Client/Error 的 module 等级补充。
- `frontend-shared.commands` 的最终三档命令。
- `frontend/vitest.sensitive.config.ts` 的 Shared 测试路径。
- `api-contract.source` 中敏感数据专项配置的影响登记。
- 测试工具中的 Shared 最终命令、路径和影响传播回归。

### 明确不做

不移动公共 Setup、Mock 或 render-router；不修改生产 HTTP Client、错误模型或 Cameras API；不把生成类型、
Backend OpenAPI 和跨端载荷检查从任务 7 提前移入本任务；不创建没有测试内容的目录。

### 实施步骤

1. 将 Route Meta 和 Sidebar Preference 迁入 `tests/unit/shared`，保留确定性输入输出与必要类型兼容检查。
2. 拆分 API Error 测试：
   - 字段路径解析、不安全路径拒绝和表单错误分组进入 unit。
   - Problem 媒体类型、Schema、status、trace 一致性以及网络/异常响应错误进入 contract。
3. 将 Axios Client 写请求失败脱敏测试迁入 contract。测试直接通过 `apiClient` 和局部 Axios adapter 构造
   含敏感值的请求，不再导入 Cameras API 或 Cameras Fixture，避免 Shared 测试依赖业务模块。
4. 在 `frontend-shared.source` 中为 `frontend/src/lib/api-client.ts` 和
   `frontend/src/lib/api-errors.ts` 增加 module 规则；保留 `src/lib/**` 的 unit 基础规则，使这两个文件变化
   会执行 unit 与 contract 目录。
5. 更新 `vitest.sensitive.config.ts`，用新的 Shared contract 路径替换
   `src/lib/api-client.test.ts` 与 `src/lib/api-errors.test.ts`，保留 Cameras 和 API Contract 的现有专项文件。
   同时把该配置文件登记为 `api-contract.source`，使配置变化会运行现有
   `check-cameras-sensitive-data.sh`，而不是在 Shared 命令中复制专项检查。
6. 将 Shared 最终命令固定为：

   ```json
   "commands": {
     "unit": [
       "cd frontend && pnpm exec vitest run tests/unit/shared"
     ],
     "module": [
       "cd frontend && pnpm exec vitest run tests/unit/shared tests/component/shared tests/contract/shared"
     ],
     "integration": [
       "cd frontend && pnpm exec vitest run tests/unit/shared tests/component/shared tests/contract/shared tests/integration/shared"
     ]
   }
   ```

7. 更新回归测试，确认命令逐层增加目录、不再包含 `src/lib`，API Client/Error 变化从 module 开始验证，
   Shared 变化仍传播到 Shell、Cameras 和 Video；敏感数据配置变化还会选择 `api-contract` 并执行现有专项
   脚本。
8. 删除四个旧测试及失去用途的辅助代码，使用 `rg` 确认敏感数据配置和命令中没有旧路径。

### 验证方式

只运行 `./scripts/verify-changed.sh`。确认 Test Infrastructure、Shared unit/contract、敏感数据专项以及受
Shared 影响的 Shell、Cameras、Video 最终命令全部通过。

### 完成标准与下一任务衔接

- Shared 测试只位于 unit 和 contract 标准目录。
- API Client 测试不依赖 Cameras 测试 Fixture 或业务 API。
- API Client/Error 源码变化会执行 contract，其他 Shared 纯规则仍从 unit 开始。
- Shared 最终命令和敏感数据配置不再引用源码旁测试；专项检查仍由 `api-contract` 唯一执行。
- 公共 Setup 与 Support 仍在旧位置并可运行，留给 06e 迁移。

下一任务统一移动公共测试基础设施并删除 `frontend/src/test/`。

## 导航

- [上一任务：06c App Shell 路由集成与收尾](./06c-app-shell-routing-and-finalization.md)
- [返回任务 6](./06-frontend-shared-app-shell.md)
- [下一任务：06e 公共 Setup、Mock 与 Router 测试工具](./06e-frontend-test-support.md)
