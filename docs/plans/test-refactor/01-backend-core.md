# 任务 1：Backend Core 测试重构

> 本任务在独立 Codex 会话中执行。实施前先阅读[总计划与通用要求](./README.md)，完成并通过统一验证入口后再进入下一任务。

### 任务目标

重构配置、应用创建、服务器入口、健康检查、HTTP 基础设施和数据库基础测试，并整理 Backend
共享 Fixture。

### 当前上下文与前置条件

现有测试分布在 `backend/tests/` 根目录、`backend/tests/api/` 和 `backend/tests/core/`，新目录使用
`backend/tests/<layer>/core/`。Core 的实现和测试分类不依赖 Cameras 或 Stream Gateway 先迁移，
适合作为 Backend 的第一个任务；但 `backend-core` 会影响这两个下游模块，因此统一验证必须在
过渡期间继续运行它们的旧测试目录。

### 实施范围

- `test_config.py`、`test_main.py`、`test_server.py`。
- 旧 `api/` 和 `core/` 下的健康检查、日志、HTTP、数据库与迁移测试。
- `backend/tests/conftest.py` 和真正跨模块复用的 `backend/tests/support/`。
- Core 对应的 unit、module、contract 和 integration 目录。
- 共享辅助代码移动后，下游测试必需的 import 更新和过渡测试命令。

### 明确不做

不重新评估 Cameras 或 Stream Gateway 的测试内容，不把 Camera 表、字段、约束和索引断言归入
Core，不改变生产行为，不为框架 wiring 机械补单元测试。对下游测试只允许修改因共享辅助代码移动
而失效的 import，以及统一验证使用的目录命令。

### 实施步骤

1. 区分可独立测试的配置/日志规则与只适合通过模块启动验证的框架 wiring。
2. 将确定性配置和日志规则迁移到 `unit/core`。
3. 将应用创建、HTTP 中间件和健康接口协作迁移到 `module/core`。
4. 将公共 HTTP 兼容性检查放入 `contract/core`。
5. 将真实数据库 Engine、Session 和 Alembic 通用迁移流程放入 `integration/core`；Camera 表结构与
   约束断言继续留在 Cameras 旧测试中，等任务 2 再迁移到 `integration/cameras`。
6. 只保留真正跨 Backend 模块使用的 Fixture；移动辅助代码后检索并更新下游测试中失效的 import，
   不借此修改下游测试行为。
7. 调整 `test-impact.json`，临时登记 Cameras 和 Stream Gateway 的旧测试路径，并让 Core 变更在
   下游尚未迁移时继续执行旧目录；增加选择器回归测试，任务 2、3 完成时再分别切换到新目录。
8. 清理 Backend 根目录和旧 `api/core` 下的业务测试。

### 验证方式

运行 `./scripts/verify-changed.sh`。脚本必须执行 Core 新目录以及 Cameras、Stream Gateway 旧目录；
数据库 integration 需要有效的 `backend/.env.local` 或 `TEST_DATABASE_URL`，不能把跳过当成通过。

### 完成标准与下一任务衔接

Backend 根目录、旧 `api/` 和旧 `core/` 不再遗留业务测试，公共 Fixture 不携带领域细节；Cameras
和 Stream Gateway 的旧测试仍能导入共享辅助代码并由统一入口执行。统一验证通过后再迁移 Cameras。

## 导航

- [返回总计划](./README.md)
- [下一任务：Backend Cameras](./02-backend-cameras.md)
