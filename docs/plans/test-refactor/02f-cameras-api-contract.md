# 任务 02f：Cameras 公共 API Contract 测试

> 本任务必须在独立 Codex 会话中执行。02e 通过统一验证入口后才能开始。实施前先阅读
> [任务 2 总说明](./02-backend-cameras.md)及其中列出的共同限制。

### 任务目标

拆分 Cameras 当前混合的 API Contract 测试，把公共 OpenAPI、生成类型和跨端载荷直接放入
`api-contract`，并为每项非 Cameras 内容确定已有模块归属。

### 当前上下文与前置条件

02a～02e 已完成。当前 `test_api_contract.py` 混合了 Cameras 请求/响应 Schema、OpenAPI、Core 健康
接口 operation id、占位实现检查和 OpenAPI 导出稳定性。`test_placeholder_gate.py` 也覆盖占位检查。
`test-impact.json` 已存在 `api-contract` 模块及 Backend/Frontend contract 标准路径。

### 实施范围

- Cameras 公共请求/响应 Schema、载荷、错误媒体类型、协议 Header、路径、operation id 和敏感字段约束。
- OpenAPI 导出稳定性，以及现有脚本对 `contracts/openapi.json` 与
  `frontend/src/generated/openapi.ts` 的检查。
- `backend/tests/contract/api_contract/`；如现有跨端检查确需测试文件，可使用
  `frontend/tests/contract/api_contract/`。
- 混合文件中 Core 健康接口检查的正确归属，以及与占位 gate 重复场景的处理。
- `api-contract` 和 `backend-cameras` 的过渡命令、影响关系及选择器回归测试。

### 明确不做

不把公共契约放入 `backend/tests/contract/cameras/`；不重复 02e 的 Router 运行行为；不手工编辑
`contracts/openapi.json`、`frontend/src/generated/openapi.ts` 或其他生成文件；不处理 MediaMTX 契约；
不修改生产行为；不删除 Cameras legacy 总目录。

### 实施步骤

1. 逐项拆分 `test_api_contract.py`：Cameras 公共 Schema、OpenAPI、载荷与导出检查直接迁入
   `backend/tests/contract/api_contract/`。
2. 把 Core 健康接口 operation id 等非 Cameras 检查并入已有
   `backend/tests/contract/core/` 合适文件；若已有同等保障则删除重复测试，不新建模块别名。
3. 将占位 handler 检查与 `test_placeholder_gate.py` 对照，只保留能够防止实际发布风险的一份；其最终
   层级按检查是否需要真实脚本/文件边界决定，不把它伪装成公共 API Contract。
4. 使用现有 `scripts/check-cameras-contracts.sh` 和敏感数据脚本检查生成 OpenAPI 与 Frontend 类型；只有
   当前脚本无法被 `api-contract` 命令执行时才最小调整命令或脚本，并补选择器回归测试。
5. 更新 `test-impact.json`，确保 `api-contract` 命令会执行 contract 测试目录和现有检查脚本，且
   Cameras API 源码变更能选择 `api-contract` 与 `backend-cameras`。仍未迁移的 persistence legacy
   必须继续由 `backend-cameras` 执行。
6. 删除 legacy 中已迁移的契约文件；保留 02g 尚需迁移的数据库、Repository 和 persistence 文件。

### 验证方式

只运行 `./scripts/verify-changed.sh`。确认 `api-contract` 实际执行 Backend contract 测试及现有生成物
检查，`backend-cameras` 仍执行剩余 persistence legacy；若升级到 integration，必须提供有效数据库
环境。

### 完成标准

- 公共 Cameras Schema、OpenAPI、生成类型和跨端载荷直接归入 `api_contract`，没有中间
  `contract/cameras` 副本。
- Core 与占位检查有明确且唯一的最终归属。
- 任务 7 只需复核选择结果，不需再次搬运本阶段测试。
- 已迁移契约不再留在 legacy，统一验证入口通过。

### 与下一任务的衔接

02g 只处理真实数据库、Repository、事务和对账持久化，并在最后删除 Cameras legacy 目录与过渡命令。

## 导航

- [上一任务：02e HTTP Module 测试](./02e-cameras-http-module.md)
- [返回任务 2](./02-backend-cameras.md)
- [下一任务：02g Persistence Integration 与迁移收尾](./02g-cameras-persistence-integration.md)
