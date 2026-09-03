# 任务 02g：Cameras Persistence Integration 与迁移收尾

> 本任务必须在独立 Codex 会话中执行。02f 通过统一验证入口后才能开始，是 Cameras 七个子任务中的
> 最后一项。实施前先阅读[任务 2 总说明](./02-backend-cameras.md)及其中列出的共同限制。

### 任务目标

迁移 Cameras 真实数据库、Repository、事务、约束、并发和对账持久化测试，删除 legacy 目录，并将
`backend-cameras` 完整切换到标准新目录。

### 当前上下文与前置条件

02a～02f 已完成并分别通过。此时 unit、module、公共 API Contract 和 Cameras support 已在最终目录，
legacy 应只剩 `test_application_persistence.py`、`test_models.py`、`test_repository.py`、
`test_reconciliation_persistence.py`、必要的占位 gate 或经前序任务确认的其他真实边界测试。执行本任务
必须有有效的 `backend/.env.local` 或 `TEST_DATABASE_URL`。

### 实施范围

- SQLAlchemy Mapper/UoW、真实 PostgreSQL Repository、事务可见性、约束、索引和迁移相关行为。
- 并发锁、写入串行化、回滚、聚合损坏读取和对账读取器/咨询锁等真实数据库风险。
- `backend/tests/integration/cameras/` 及其数据库 Fixture。
- `backend-cameras` 最终 tests/commands、模块影响关系和选择器回归测试。
- legacy Cameras 测试目录和失去用途的辅助代码清理。

### 明确不做

不修改生产代码或数据库结构，不重构 Stream Gateway、Frontend 或任务 7 的其他契约，不搭建 E2E，
不把缺少数据库环境或跳过 integration 当成通过。

### 实施步骤

1. 重新评估剩余 persistence 测试要保护的真实边界，合并重复的数据库准备和只重复 unit/module 行为
   的场景；保留 PostgreSQL 特有约束、事务、并发和映射风险。
2. 将 Fake Repository/UoW 自身的确定性共享检查保留在 `support/cameras` 或最低有效层级；只有正确性
   依赖真实 SQLAlchemy/PostgreSQL 的测试进入 `backend/tests/integration/cameras/`。
3. 迁移模型约束、Repository、事务与对账 persistence 测试，复用
   `backend/tests/support/database.py`，避免复制 Core 已提供的数据库 Fixture。
4. 对大型 Repository 测试按风险分组；可以按职责拆文件，但不改变被测生产行为，也不为目录完整增加
   场景。
5. 删除 `backend/tests/modules/cameras/` 中最后的测试、helper 和空目录，并用 `rg` 确认没有 import 或
   命令继续引用该路径。
6. 最终更新 `test-impact.json`：移除 Cameras legacy tests 路径和过渡命令；`backend-cameras` 的 unit、
   module、integration 命令按层级运行新 `unit/cameras`、`module/cameras` 和
   `integration/cameras`。公共契约继续由独立 `api-contract` 命令负责。
7. 更新选择器回归测试，确认 Cameras 源码在不同风险等级选择正确新目录，Stream Gateway 对 Cameras
   的影响不再引用 legacy，未登记生产源码仍会使检查失败。

### 验证方式

在有效数据库环境下只运行 `./scripts/verify-changed.sh`。确认真实 PostgreSQL integration 实际执行且
没有跳过，摘要中不再出现 `backend/tests/modules/cameras/`。失败时按脚本给出的临时日志路径用 `rg`
定位，不手工缩小范围替代最终验证。

### 完成标准

- Cameras unit、module、integration 和专用 support 均位于标准目录；公共契约位于
  `contract/api_contract`。
- `backend/tests/modules/cameras/` 及所有 Cameras legacy 命令已删除，没有残留 import。
- `test-impact.json` 能按层级执行 Cameras 新目录，Stream Gateway 的影响关系继续有效。
- 统一验证入口在实际数据库 integration 执行后通过。

### 与下一任务的衔接

任务 2 到此完成。将最终新目录、`test-impact.json` 命令和验证结果交给任务 3；任务 3 可据此确认
Stream Gateway 变更会触发 Cameras 的新 module 测试。

## 导航

- [上一任务：02f 公共 API Contract 测试](./02f-cameras-api-contract.md)
- [返回任务 2](./02-backend-cameras.md)
- [下一总任务：Backend Stream Gateway](./03-backend-stream-gateway.md)
