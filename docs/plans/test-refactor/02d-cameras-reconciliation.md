# 任务 02d：Cameras 后台对账 Unit / Module 测试

> 本任务必须在独立 Codex 会话中执行。02c 通过统一验证入口后才能开始。实施前先阅读
> [任务 2 总说明](./02-backend-cameras.md)及其中列出的共同限制。

### 任务目标

迁移媒体对账计划、锁竞争、失败恢复、退避和日志规则测试，使纯计算与模块协作分层清楚且执行
确定，不依赖真实 PostgreSQL、MediaMTX 或实际休眠。

### 当前上下文与前置条件

02a～02c 已完成。现有 `test_media_reconciliation.py` 同时覆盖纯计划计算、单轮协作、后台 Runner、
降级状态和日志；`test_reconciliation_persistence.py` 的真实数据库行为留给 02g。

### 实施范围

- 对账计划中 missing、drift、orphan、unmanaged 等确定性计算。
- 锁未获得、快照/读取失败、部分写失败、下一轮恢复、取消传播等模块协作。
- 指数退避、jitter、失败提醒、恢复状态和敏感日志规则。
- 本阶段所需的 Fake、时钟/随机源、过渡命令和选择器回归测试。

### 明确不做

不迁移真实 PostgreSQL 读取器、咨询锁和连接池行为；不使用真实 sleep；不访问真实 MediaMTX；不修改
生产行为；不删除 legacy 总目录。

### 实施步骤

1. 将无 I/O 的对账计划和确定性状态计算迁入 `backend/tests/unit/cameras/`。
2. 将单轮对账、Runner、锁竞争、错误恢复和日志协作迁入
   `backend/tests/module/cameras/`，以 Fake 边界和可控时钟/随机源替代真实等待。
3. 合并只因 Mock 排列不同但保护同一风险的场景，保留写入顺序、零写入、安全日志等外部可见规则。
4. 确认 `test_reconciliation_persistence.py` 仍完整留在 legacy，等待 02g 的真实数据库迁移。
5. 更新 `backend-cameras` 过渡命令，使新 unit、module 与剩余 legacy 同时执行，并更新选择器回归测试。
6. 删除 legacy 中已迁移的非持久化对账文件及失去用途的辅助代码。

### 验证方式

只运行 `./scripts/verify-changed.sh`。确认对账 unit/module 不依赖实际时间等待，且剩余 persistence
legacy 仍会执行；脚本升级到 integration 时必须提供有效数据库环境。

### 完成标准

- 纯计划计算位于 unit，单轮与 Runner 协作位于 module。
- 测试无真实 sleep、无真实数据库和 MediaMTX 依赖，敏感日志规则仍有明确覆盖。
- 已迁移对账测试不再留在 legacy，统一验证入口通过。

### 与下一任务的衔接

02e 只迁移 HTTP 运行行为；对账 persistence 文件继续保留至 02g。

## 导航

- [上一任务：02c 查询流程 Module 测试](./02c-cameras-query-module.md)
- [返回任务 2](./02-backend-cameras.md)
- [下一任务：02e HTTP Module 测试](./02e-cameras-http-module.md)
