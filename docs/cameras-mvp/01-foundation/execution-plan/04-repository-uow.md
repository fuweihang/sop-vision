# 步骤 4｜Repository 与事务边界

> 前置：[步骤 1](./01-database-runtime.md)、[步骤 2](./02-relational-schema.md)、[步骤 3](./03-domain-model.md)  
> 产出：Camera 专用 Repository、Unit of Work、ORM 映射和事务 Fixture

## 1. 完成目标

提供后续功能切片可直接使用的持久化端口，使 Camera 与完整 Source 集合始终作为一个聚合读取和保存，并由一个明确的 Unit of Work 控制提交。

## 2. 端口范围

定义 Cameras MVP 已有消费者需要的能力：

```text
CameraRepository
├── add(aggregate)
├── get(camera_id, for_update=false)
├── list(criteria, page, page_size, sort)
├── count(criteria)
└── delete(aggregate)

CameraUnitOfWork
├── cameras
├── commit()
└── rollback()
```

列表 criteria 只表达已冻结的名称/IP 搜索和排序，不接受任意列名、SQL 文本或通用过滤字典。不要建立 GenericRepository。

## 3. 映射与事务规则

- ORM 模型是基础设施对象，领域实体不继承 SQLAlchemy Base。
- Repository 读取时一次重建完整聚合，Source 始终按 `sort_order` 排序。
- 新建聚合在同一事务写 Camera 和 Source，并利用延迟复合外键设置默认源。
- 完整更新由后续业务 Service 计算意图；Repository 负责持久化新增、保留、删除和排序结果。
- `flush` 可用于尽早发现约束冲突，但只有 Unit of Work 可以 commit。
- `get(..., for_update=true)` 为更新/删除切片提供行锁；普通查询不加锁。
- 数据库 IntegrityError 只映射已知稳定约束；未知约束作为基础设施错误上抛并保留 trace，不把 SQL 文本暴露给客户端。
- Session 和领域对象不得跨请求共享。

## 4. Fixture 与测试隔离

- `CameraBuilder` 使用固定 UUID 和时钟构建领域聚合。
- PostgreSQL 集成测试每例运行在可回滚事务或独立 schema 中，不能依赖执行顺序。
- 提供 Fake Repository/Fake Unit of Work，供 02–09 功能切片在无 PostgreSQL 时测试 Application Service。
- Fake 必须遵循真实实现的聚合边界和排序语义，不能暴露真实实现没有的便利方法。

## 5. 实施顺序

1. 定义 Repository/UoW Protocol 和查询值对象。
2. 实现领域实体与 ORM row 的显式双向映射。
3. 实现 add/get，并覆盖完整聚合与排序。
4. 实现 list/count 的稳定排序和分页底层能力。
5. 实现 delete 和 `for_update`。
6. 增加 Fake、Fixture 和真实 PostgreSQL 契约测试，确保两种实现行为一致。

## 6. 必测场景

- 单 Source/多 Source round-trip 后 ID、时间、默认源和顺序不变。
- add 后不 commit 则其他事务不可见；rollback 后无残留。
- Camera 删除依赖数据库级联，Source 无残留。
- 同一 Camera 规范化后缀竞态最终由数据库约束阻止，并映射为稳定持久化错误。
- list 先搜索、再计数、再稳定排序分页；相同主排序值使用 `camera_id` 升序。
- `for_update` 能串行化同一 Camera 的并发写意图。
- 损坏数据无法重建为看似合法的聚合。

## 7. 退出条件

- 后续业务 Service 只依赖 Repository/UoW Protocol 即可编写单元测试。
- 所有聚合写操作都能在单事务成功或完整回滚。
- Fake 与 PostgreSQL 实现通过同一组 Repository contract tests。
- Repository 不访问 MediaMTX，不构造 HTTP 响应，不记录凭据。

## 8. 后续交接

步骤 5/6 不直接依赖 SQLAlchemy；功能切片通过 FastAPI dependency 注入 Unit of Work。创建、更新和删除切片只能在数据库提交后执行 MediaMTX 尽力操作。
