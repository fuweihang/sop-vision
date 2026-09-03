# Backend 测试层级

应选择能够可靠捕获风险的最低层级进行测试。

## 单元测试 (Unit)

适用于隔离的业务规则、计算逻辑、状态转换、数据校验、权限判定及确定性转换逻辑。

避免针对透传式服务方法、框架胶水代码（wiring）或仅断言内部方法被调用的 Mock 对象编写单元测试。

目录：`backend/tests/unit/<module>/...`

## 模块测试 (Module)

适用于同一个 Backend 业务模块内的 API、Application、Domain 等多层协作。进程外边界应替换为轻量 Fake，避免模块测试因 PostgreSQL 或 MediaMTX 是否启动而波动。

目录：`backend/tests/module/<module>/...`

## 集成测试 (Integration)

适用于正确性依赖于真实边界或组件协作的场景，例如数据库行为、事务、仓储（Repository）映射、文件系统、缓存、消息队列、HTTP 客户端行为、序列化或多个后端组件的协同工作。

在条件允许的情况下，优先测试真实边界，而非过度 Mock 内部实现细节。

目录：`backend/tests/integration/<module>/...`

## 契约测试 (Contract)

适用于变更公共契约或跨模块契约的场景，例如 HTTP 模式（Schema）、事件/消息模式、序列化载荷（Payload）、公共接口或兼容性规则。

契约测试应侧重于保障兼容性，而非重复测试服务的各项具体行为。

目录：`backend/tests/contract/<module>/...`

## 端到端测试 (E2E)

仅针对少量关键的跨系统业务流程使用，且仅在低层级测试无法提供足够信心时采用。

切勿为常规的 CRUD 操作或每一个 API 接口编写 E2E 测试。

项目当前没有日常 E2E 测试入口。确有必要时先设计独立的运行环境和影响规则，不要直接混入 integration 目录。
