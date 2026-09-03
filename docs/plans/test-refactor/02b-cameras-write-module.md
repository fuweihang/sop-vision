# 任务 02b：Cameras 写流程 Module 测试

> 本任务必须在独立 Codex 会话中执行。02a 通过统一验证入口后才能开始。实施前先阅读
> [任务 2 总说明](./02-backend-cameras.md)及其中列出的共同限制。

### 任务目标

迁移 Cameras 创建、完整更新和默认预览源修改的应用流程测试，用模块公开行为验证事务、媒体协作和
安全错误处理。

### 当前上下文与前置条件

02a 已建立 `backend/tests/support/cameras/` 和 unit 测试。写流程测试当前主要位于
`test_camera_create.py`、`test_camera_update.py`、`test_default_preview_source.py`，可使用轻量 Fake
隔离 PostgreSQL 与 MediaMTX。

### 实施范围

- 创建 Camera、更新 Camera、设置默认预览源的应用层协作。
- 提交前失败的回滚、取消传播、提交后媒体失败降级和安全错误输出。
- `backend/tests/module/cameras/` 中与写流程有关的测试。
- 本阶段所需的 support 调整、legacy import、过渡命令和选择器回归测试。

### 明确不做

不迁移查询流程、HTTP Router、后台对账、公共契约或真实 Repository；不通过 Mock 调用次数固定内部
实现顺序；不修改生产行为；不删除 legacy 总目录。

### 实施步骤

1. 按“提交前可回滚”和“提交后只能降级”两条业务边界重新评估现有场景，合并重复的异常排列。
2. 使用 02a 的轻量 Fake 表达持久化与媒体边界，断言最终返回、事务结果、外部可见操作顺序和敏感
   信息保护，不断言无业务意义的内部调用次数。
3. 将有价值的创建、更新、默认源流程迁入 `backend/tests/module/cameras/`。
4. 仅在后续 legacy 测试确有需要时补充 `support/cameras`，同步更新其 import。
5. 更新 `backend-cameras` 过渡命令，使新 unit、当前 module 写流程和剩余 legacy 同时执行，并更新
   选择器回归测试。
6. 删除 legacy 中已迁移的写流程文件，保留尚未迁移的查询、对账、HTTP、契约与 persistence 文件。

### 验证方式

只运行 `./scripts/verify-changed.sh`。确认新 unit、module 写流程和剩余 legacy 都由
`backend-cameras` 执行；数据库 integration 被选择时必须提供有效数据库环境。

### 完成标准

- 三类写流程通过模块公开行为覆盖，不依赖真实 PostgreSQL 或 MediaMTX。
- 重复、仅验证 Mock 交互或私有实现的测试已合并或删除。
- 已迁移写流程不再留在 legacy，统一验证入口通过。

### 与下一任务的衔接

02c 复用相同的 Fake 和错误断言方式迁移详情、列表查询；写流程测试保持在
`module/cameras`，不与 HTTP 测试合并。

## 导航

- [上一任务：02a 测试辅助代码与 Unit 测试](./02a-cameras-support-and-unit.md)
- [返回任务 2](./02-backend-cameras.md)
- [下一任务：02c 查询流程 Module 测试](./02c-cameras-query-module.md)
