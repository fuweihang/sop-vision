# 任务 02c：Cameras 查询流程 Module 测试

> 本任务必须在独立 Codex 会话中执行。02b 通过统一验证入口后才能开始。实施前先阅读
> [任务 2 总说明](./02-backend-cameras.md)及其中列出的共同限制。

### 任务目标

迁移 Camera 详情与列表查询流程，验证分页、运行状态投影、网关降级、数据损坏和取消传播等模块
公开行为。

### 当前上下文与前置条件

02a、02b 已提供 Cameras support、unit 和写流程 module 测试。查询测试当前主要位于
`test_camera_detail.py` 和 `test_camera_list.py`，其 HTTP 对应文件仍留给 02e。

### 实施范围

- Camera 详情和列表的应用层查询流程。
- count/page、空页、搜索与分页条件、单次媒体快照、离线降级和安全错误。
- 数据库失败、聚合损坏、未知网关错误和任务取消的可观察结果。
- 本阶段所需的 support 调整、legacy import、过渡命令和选择器回归测试。

### 明确不做

不迁移 HTTP Router 或 Schema，不迁移后台对账和真实数据库读取，不重复 02a 已覆盖的状态计算纯规则，
不修改生产行为，不删除 legacy 总目录。

### 实施步骤

1. 区分查询流程新增风险与 HTTP 层映射风险，删除将相同业务行为在两层重复断言的部分。
2. 使用 Fake Repository、UoW 与媒体网关覆盖详情、列表的成功、降级和必要失败路径。
3. 只断言事务结束后的可见结果、分页数据、媒体快照使用和安全错误，不固定无意义的内部调用次数。
4. 将有价值的查询流程迁入 `backend/tests/module/cameras/`，复用既有 support。
5. 更新 `backend-cameras` 过渡命令，使新 unit、已迁移 module 和剩余 legacy 同时执行，并更新选择器
   回归测试。
6. 删除 legacy 中已迁移的查询流程文件，保留对账、HTTP、契约与 persistence 文件。

### 验证方式

只运行 `./scripts/verify-changed.sh`。确认详情和列表的新 module 测试及剩余 legacy 均被执行；脚本
升级到 integration 时必须提供有效数据库环境。

### 完成标准

- 详情和列表行为由确定性的模块测试覆盖，不访问真实数据库或 MediaMTX。
- HTTP 文件不再承担应用层重复断言的唯一保障。
- 已迁移查询流程不再留在 legacy，统一验证入口通过。

### 与下一任务的衔接

02d 使用现有 Cameras support 拆分后台对账的纯计划计算和协作流程；查询测试无需随对账任务调整。

## 导航

- [上一任务：02b 写流程 Module 测试](./02b-cameras-write-module.md)
- [返回任务 2](./02-backend-cameras.md)
- [下一任务：02d 后台对账 Unit / Module 测试](./02d-cameras-reconciliation.md)
