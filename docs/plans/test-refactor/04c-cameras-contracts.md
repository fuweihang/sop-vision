# 任务 04c：API Client 与公共生成物检查

> 本任务必须在独立 Codex 会话中执行。04b 通过统一验证入口后才能开始。实施前先阅读
> [任务 4 总说明](./04-frontend-cameras.md)及其中列出的共同限制。

### 任务目标

分开 Cameras 模块自己的 API Client 边界与公共 OpenAPI/生成类型检查，修正当前敏感数据测试仍位于
`frontend/src/test/` 的遗留问题。

### 当前上下文与前置条件

`cameras-api.test.ts` 验证六个 operation 的方法、路径、参数和请求体；
`cameras-contract-security.test.ts` 读取公共 OpenAPI 与生成类型，并由
`vitest.sensitive.config.ts` 和 `check-cameras-sensitive-data.sh` 执行。前者属于 Cameras 模块，后者
属于 `api-contract`，不能放入同一个目录。

### 实施范围

- `frontend/tests/contract/cameras/` 中的 Cameras API Client 检查。
- `frontend/tests/contract/api_contract/` 中的生成物敏感数据检查。
- `frontend/vitest.sensitive.config.ts` 的最小路径修改。
- `test-impact.json` 和 Test Infrastructure 中与两个 Contract 目录、专项脚本有关的回归测试。

### 明确不做

不重新生成或手工修改 OpenAPI/TypeScript 生成物，不迁移共享 `api-client`/`api-errors` 测试，不测试
页面行为，不把公共检查复制到 `contract/cameras`。

### 实施步骤

1. 迁移 Cameras operation Client 的方法、路径、参数编码、请求体和响应边界测试到
   `contract/cameras`，删除共置旧文件。
2. 迁移生成物敏感数据测试到 `contract/api_contract`，更新 sensitive Vitest 配置中的 include 路径。
3. 保留 `api-contract` 模块调用现有 `check-cameras-sensitive-data.sh`；确认该脚本实际执行新测试文件。
4. 更新过渡命令与选择器回归测试：`contract/cameras` 选择 Cameras module 级验证，
   `contract/api_contract` 选择 `api-contract` 并继续影响 Backend/Frontend Cameras。

### 验证方式

只运行 `./scripts/verify-changed.sh`，确认 API Contract、Frontend Cameras、Frontend Shared 过渡命令和
Test Infrastructure 均通过，敏感数据专项脚本没有因路径变化漏掉测试。

### 完成标准与下一任务衔接

- 模块 API Client 与公共生成物检查各自只有一个归属。
- `frontend/src/test/cameras-contract-security.test.ts` 不再存在。
- 任务 7 只复核归属和选择结果，不再次移动这些测试。

下一任务开始迁移不依赖视频 Session 和写入流程的基础组件。

## 导航

- [上一任务：04b Cameras Unit 测试](./04b-cameras-unit.md)
- [返回任务 4](./04-frontend-cameras.md)
- [下一任务：04d 基础组件行为](./04d-cameras-components.md)
