# 任务 02e：Cameras HTTP Module 测试

> 本任务必须在独立 Codex 会话中执行。02d 通过统一验证入口后才能开始。实施前先阅读
> [任务 2 总说明](./02-backend-cameras.md)及其中列出的共同限制。

### 任务目标

迁移 Cameras HTTP Router 的运行行为测试，只保留 HTTP 层新增的状态码、Header、Problem Details、
请求解析和依赖覆盖风险。

### 当前上下文与前置条件

02b、02c 已稳定覆盖写入和查询的应用流程。HTTP 测试当前主要位于
`test_camera_create_api.py`、`test_camera_update_api.py`、`test_default_preview_source_api.py`、
`test_camera_detail_api.py` 和 `test_camera_list_api.py`。公共 Schema/OpenAPI 兼容性留给 02f。

### 实施范围

- 创建、更新、默认源、详情和列表 Router 的 HTTP 运行行为。
- 成功与错误状态码、缓存/位置等协议 Header、Problem Details 映射、参数解析和依赖覆盖。
- 敏感输入不进入响应和日志的 HTTP 边界风险。
- 本阶段所需的应用 Fixture、过渡命令和选择器回归测试。

### 明确不做

不重复应用层事务、媒体顺序或 Repository 行为；不把 OpenAPI、生成类型和跨端载荷放入
`contract/cameras`；不使用真实数据库或 MediaMTX；不修改生产行为；不删除 legacy 总目录。

### 实施步骤

1. 对照 02b、02c 已覆盖的行为，移除 HTTP 文件中重复的业务内部断言，只保留协议层能发现的缺陷。
2. 使用 FastAPI 应用和依赖覆盖测试请求解析、响应状态、Header 与 Problem Details；进程外边界使用
   `support/cameras` 的 Fake。
3. 将测试迁入 `backend/tests/module/cameras/`，请求/响应公共 Schema 的结构兼容性留在 legacy
   `test_api_contract.py` 等待 02f。
4. 检查错误正文、日志和默认 repr 不泄漏凭据、完整 RTSP URL 或请求原文，避免与 02f 的静态契约
   检查重复。
5. 更新 `backend-cameras` 过渡命令，使新 unit/module 与剩余 legacy 同时执行，并更新选择器回归测试。
6. 删除 legacy 中已迁移的 HTTP 测试文件，保留公共契约和 persistence 文件。

### 验证方式

只运行 `./scripts/verify-changed.sh`。确认所有 HTTP module 测试和剩余 legacy 被执行；脚本升级到
integration 时必须提供有效数据库环境。

### 完成标准

- Cameras HTTP 运行行为位于 `backend/tests/module/cameras/`，只覆盖 HTTP 层新增风险。
- 应用层行为没有在 HTTP 文件中重复维护，公共契约仍明确留给 02f。
- 已迁移 HTTP 测试不再留在 legacy，统一验证入口通过。

### 与下一任务的衔接

02f 拆分混合的 API Contract 文件，把 Cameras 公共 Schema、OpenAPI、生成类型和跨端载荷直接归入
`api-contract`；不会把 HTTP 运行行为重新移动到 contract。

## 导航

- [上一任务：02d 后台对账 Unit / Module 测试](./02d-cameras-reconciliation.md)
- [返回任务 2](./02-backend-cameras.md)
- [下一任务：02f 公共 API Contract 测试](./02f-cameras-api-contract.md)
