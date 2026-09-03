# 任务 2：Backend Cameras 测试重构

> 本任务规模较大，已拆成 02a～02g 七个顺序任务。每个子任务必须在独立 Codex 会话中执行，
> 前一项通过统一验证入口后才能开始下一项，禁止并行修改同一工作区。

### 任务目标

重新评估 Cameras 的领域规则、应用流程、后台对账、HTTP、公共 API Contract、Repository 和真实
数据库测试，使每个测试只有一个层级和模块归属，并移除旧的
`backend/tests/modules/cameras/` 测试目录。

### 当前上下文与前置条件

任务 1 已整理 Backend 公共 Fixture，并在 `test-impact.json` 中保留 Cameras 旧目录命令。当前 Cameras
测试主要位于 `backend/tests/modules/cameras/`，约 23 个测试文件，混合了纯规则、模块协作、公共
契约和 PostgreSQL 集成行为，不能在一个会话中可靠完成。

开始每个子任务前，都要重新读取当前版本的 `AGENTS.md`、总计划、`test-policy`、`test-impact.json`
和该子任务方案。生产代码行为默认不在本任务范围内；发现问题时记录，不借测试迁移修改生产实现。

### 已确定的归属

- Cameras 专用 Builder、Fake、常量和 Repository 共享检查放入
  `backend/tests/support/cameras/`，不放在业务测试目录。
- 纯规则放入 `backend/tests/unit/cameras/`；模块内业务协作和 HTTP 运行行为放入
  `backend/tests/module/cameras/`；真实数据库、事务和 Repository 行为放入
  `backend/tests/integration/cameras/`。
- 公共 OpenAPI、生成类型和跨端载荷属于 `api-contract`，直接进入
  `backend/tests/contract/api_contract/` 或 `frontend/tests/contract/api_contract/`。不先放入
  `contract/cameras` 再由任务 7 二次搬运。
- Cameras 请求/响应 Schema 若只保护公共 HTTP 兼容性，也属于 `api-contract`；HTTP 状态码、Header、
  Problem Details 映射和依赖覆盖属于 `module/cameras`。
- 任务 7 只复核跨端契约的唯一归属和选择结果，不再次迁移任务 02 已处理的公共契约测试。

### 所有子任务共同限制

1. 七个子任务必须严格按 02a～02g 串行执行。
2. 每个阶段先判断测试要防止的缺陷，再决定保留、合并、重写或删除；不机械搬文件。
3. 02a～02f 处于过渡期。每个阶段都要更新 `test-impact.json` 和选择器回归测试，使
   `backend-cameras` 同时运行已经迁移的新目录与仍未迁移的 legacy 目录。不能因为新目录已经存在就
   提前移除 `backend/tests/modules/cameras/` 命令。
4. 已迁移测试应从 legacy 删除，避免同一测试重复执行；未迁移文件继续留在 legacy 并由统一入口执行。
5. 每个阶段交付前只运行 `./scripts/verify-changed.sh`。脚本选择数据库 integration 时，必须提供
   `backend/.env.local` 或 `TEST_DATABASE_URL`，不能把跳过当成通过。
6. 只有 02g 可以删除 legacy 目录和命令，并把 `backend-cameras` 完整切换到标准新目录。
7. 不新增 Cameras E2E，不修改生成文件 `contracts/openapi.json` 和
   `frontend/src/generated/openapi.ts`；需要检查生成结果时使用项目现有脚本。

### 子任务执行顺序

1. [02a：测试辅助代码与 Unit 测试](./02a-cameras-support-and-unit.md)
2. [02b：写流程 Module 测试](./02b-cameras-write-module.md)
3. [02c：查询流程 Module 测试](./02c-cameras-query-module.md)
4. [02d：后台对账 Unit / Module 测试](./02d-cameras-reconciliation.md)
5. [02e：HTTP Module 测试](./02e-cameras-http-module.md)
6. [02f：公共 API Contract 测试](./02f-cameras-api-contract.md)
7. [02g：Persistence Integration 与迁移收尾](./02g-cameras-persistence-integration.md)

### 任务 2 完成标准与下一任务衔接

七个子任务全部通过后，Cameras 测试位于标准目录，专用辅助代码位于 `support/cameras`，公共 API
契约直接位于 `api_contract`，旧 Cameras 测试目录和过渡命令已删除。此时
`backend-stream-gateway` 触发的 Cameras 测试必须使用新命令，之后才能进入任务 3。

## 导航

- [返回总计划](./README.md)
- [首先执行：02a 测试辅助代码与 Unit 测试](./02a-cameras-support-and-unit.md)
- [任务 2 完成后：Backend Stream Gateway](./03-backend-stream-gateway.md)
