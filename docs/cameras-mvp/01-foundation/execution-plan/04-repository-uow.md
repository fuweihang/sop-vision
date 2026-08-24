# 步骤 4｜Repository 与事务边界

> 前置：[步骤 1](./01-database-runtime.md)、[步骤 2](./02-relational-schema.md)、[步骤 3](./03-domain-model.md)  
> 产出：Camera 专用 Repository、Unit of Work、显式 ORM 映射和事务 Fixture

## 1. 完成目标

提供后续功能切片可直接使用的持久化端口，使 Camera 与完整 Source 集合始终作为一个
聚合读取、保存和删除，并由一个明确的 Unit of Work 控制提交。Application Service 只依赖
领域对象和本步骤定义的 Protocol，不接触 `AsyncSession`、ORM Row、SQLAlchemy 异常或
步骤 2 的 Row 级 Repository。

本步骤不新增 Camera HTTP 路由、不访问 MediaMTX、不修改表结构或迁移，也不建立通用
Repository/Base Service。

## 2. 公共端口与类型

公共端口固定为异步 Protocol：

```text
CameraRepository
├── add(camera: Camera) -> None
├── save(camera: Camera) -> None
├── get(camera_id: CameraId, for_update: bool = false) -> Camera | None
├── list(criteria: CameraListCriteria, page: int, page_size: int) -> tuple[Camera, ...]
├── count(criteria: CameraListCriteria) -> int
└── delete(camera_id: CameraId) -> Camera | None

CameraUnitOfWork
├── cameras: CameraRepository
├── commit() -> None
└── rollback() -> None
```

- `add` 只接受尚未持久化的新聚合；Camera 或 Source 主键已存在时不得隐式转为更新。
- `save` 只接受已存在的完整聚合；目标不存在时抛稳定的 `CameraNotFoundError`，不得插入新
  Camera。
- `get` 查无结果返回 `None`。持久化数据无法重建时抛步骤 3 的
  `CameraAggregateCorruptedError`，不得返回部分 Source 或静默修复数据。
- `delete` 在自己的锁内读取数据库中的最新完整聚合，显式删除全部 Source 和 Camera，返回
  被删除聚合；目标不存在时返回 `None`。返回值供业务 Service 在提交后提取 Source ID 并
  执行 MediaMTX 尽力清理。
- `CameraListCriteria` 是不可变值对象，只包含规范化后的 `q: str | None`。它不接受任意列名、
  SQL、通用过滤字典或排序字段。
- `page/page_size` 由步骤 5 保证合法；Repository 仍不得接受负 offset，也不得绕过
  `page_size <= 100` 的公共上限。

建议把 Protocol 和查询值对象放在 Cameras application 边界，把 SQLAlchemy 实现、Mapper、
约束转换器和 UoW 放在 `persistence/`，把 Fake 与 Store 放在 Cameras 测试支持模块。现有
`CameraPersistenceRepository` 只作为适配器内部的行锁与无外键引用完整性能力复用，不再向
Application Service 暴露 ORM Row。

## 3. 查询、搜索与固定排序

Camera 列表没有可选排序。所有调用固定按以下顺序分页：

```sql
ORDER BY cameras.created_at ASC, cameras.camera_id ASC
```

先应用搜索条件，再由 `count(criteria)` 计算真实总数；`list` 使用同一搜索条件，并在排序后
执行 `OFFSET (page - 1) * page_size LIMIT page_size`。超过最后一页时返回空 tuple，不修正
调用方页码。

`q` 的语义固定如下：

1. 步骤 5 先 trim；空白字符串转换为 `None`，非空最长 100 字符。
2. 查询名称和 PostgreSQL `host(cameras.ip_address)` 的文本形式。
3. 使用不区分大小写的包含匹配。
4. `%`、`_` 和 `\` 都是用户输入的普通字符，构造 `ILIKE` 前分别转义，并显式声明
   `ESCAPE '\'`，不能让输入改变为 SQL 通配模式。
5. SQL 必须使用绑定参数，不能拼接原始查询文本。

Fake 使用相同的 trim 后 criteria 和字面包含规则，并使用 `casefold()` 实现大小写无关比较。
共享契约测试使用 ASCII 大小写、中文、IPv4 和 `%/_/\` 字面量覆盖两种实现；不把数据库
locale 未冻结的其他 Unicode 排序或大小写规则扩展为产品契约。

## 4. 显式映射与聚合读取

- ORM Row 是基础设施对象；`Camera/CameraSource` 不继承 SQLAlchemy Base，也不持有 Row。
- Mapper 显式实现 `Camera -> CameraRow/CameraSourceRow` 和 Row 集合到
  `Camera.reconstitute(...)` 的双向转换，不复制步骤 3 的规范化或不变量逻辑。
- 密码只在写 Row 和调用 `Camera.reconstitute` 时显式读取；Mapper、Row、异常和日志的
  `repr/str` 不得输出密码或完整 RTSP URL。
- `get/list/delete` 必须在 Session 有效期内一次取得重建聚合所需的 Camera 与全部 Source。
  可以使用显式的两段查询或安全的 eager loading，但不得依赖 AsyncSession lazy loading、
  产生逐 Camera N+1，或在 Session 关闭后再访问 Row 属性。
- Source 读取查询固定按 `sort_order ASC`；Mapper 不得在内存中修补断裂、重复或负数顺序。
  `Camera.reconstitute` 负责把损坏数据转换为稳定的聚合损坏错误。
- 普通 `get/list/count` 不加行锁，也不执行无意义的 commit。

## 5. 写入差异与加锁顺序

所有既有 Camera 的写操作采用同一锁顺序，避免无外键表之间产生孤儿或死锁：

1. `SELECT cameras ... FOR UPDATE` 锁定 Camera；不存在时按对应端口契约返回 `None` 或抛
   `CameraNotFoundError`。
2. 按 `source_id ASC` 查询并 `FOR UPDATE` 锁定该 Camera 的全部 Source。
3. 完成所有权校验、差异写入和 flush。

具体写语义：

- `add` 在同一事务插入 Camera 和全部 Source，flush 后再次锁定并确认默认 Source 存在且
  `camera_id` 属于新 Camera；只有 UoW 可以提交。
- `save` 以 `source_id` 比较锁内数据库集合与传入完整聚合：保留项更新可变字段与时间，
  新 ID 插入，数据库中存在但聚合中缺失的项显式删除；最后写入连续 `sort_order`、Camera
  字段和 `default_preview_source_id`。
- 传入 `save` 的所有已有 Source 必须属于目标 Camera；未知或属于其他 Camera 的 Source ID
  作为服务端聚合不变量错误失败，不能被当作新增项。
- 后缀与顺序唯一约束保持 `DEFERRABLE INITIALLY DEFERRED`，允许同一事务安全交换两个
  Source 的 `url_suffix` 或 `sort_order`；不得通过临时魔法后缀或负数顺序绕开约束。
- `delete` 按上述顺序锁定并重建最新聚合，先显式删除全部 Source，再删除 Camera，flush 后
  返回删除前聚合。任何失败都由同一个 UoW 完整回滚。
- 同一事务内重复调用 `get(..., for_update=true)`、`save` 或 `delete` 可以重入已有数据库锁，
  但实现仍必须保持 Camera → Source 的顺序。

## 6. Unit of Work 与 Session 生命周期

- FastAPI dependency 或任务 composition root 使用步骤 1 的 factory 创建并关闭独立
  `AsyncSession`，再把同一个 Session 注入 SQLAlchemy Repository 和 UoW。
- UoW 不创建、不关闭 Session，不实现隐式 commit，也不持有跨请求状态。一个 UoW 只服务
  一个顺序执行的业务用例，禁止跨请求、线程或并发 asyncio task 共享。
- UoW 创建时暴露唯一的 `cameras` Repository；同一 UoW 内所有 Repository 操作共享同一
  Session 和数据库事务。
- `commit()` 调用 `AsyncSession.commit()`；`rollback()` 调用 `AsyncSession.rollback()`，
  两者均可由 Application Service 显式调用。
- 请求/任务依赖正常退出时只关闭 Session，不自动 commit。Application Service 忘记 commit
  的写入不得落库。
- 业务异常、任务取消或其他异常由依赖边界 rollback 后原样上抛。`flush` 或 `commit` 失败时
  必须先 rollback，使 Session 离开 failed transaction 状态，再转换或重新抛出异常。
- 数据库提交后的 MediaMTX 更新、释放或状态投影不属于 UoW；创建、更新和删除 Service 只能
  在 `commit()` 成功后调用这些外部能力，外部失败不能伪装成数据库回滚。

## 7. 稳定约束错误

定义不携带 SQL、参数、约束名或原始 Row 的：

```text
CameraConstraintViolationError(kind: CameraConstraintViolationKind)
CameraPersistenceOperationError()
```

`CameraConstraintViolationKind` 至少覆盖：

| 数据库约束 | kind | 对外语义 |
| --- | --- | --- |
| `pk_cameras` | `CAMERA_ID_ALREADY_EXISTS` | 服务端 ID/持久化不变量错误 |
| `pk_camera_sources` | `SOURCE_ID_ALREADY_EXISTS` | 服务端 ID/持久化不变量错误 |
| `uq_camera_sources_camera_id_url_suffix` | `DUPLICATE_SOURCE_SUFFIX` | 后续 HTTP 层可映射为字段错误 |
| `uq_camera_sources_camera_id_sort_order` | `DUPLICATE_SOURCE_ORDER` | 服务端聚合不变量错误 |
| `ck_cameras_ip_address_ipv4` | `INVALID_CAMERA_IP` | 服务端聚合不变量错误 |
| `ck_cameras_rtsp_port_range` | `INVALID_RTSP_PORT` | 服务端聚合不变量错误 |
| `ck_camera_sources_sort_order_non_negative` | `INVALID_SOURCE_ORDER` | 服务端聚合不变量错误 |

- Repository 的 `flush` 和 UoW 的 `commit` 共用同一个约束转换函数，因为延迟唯一约束通常到
  commit 才报错。
- 转换器只读取 PostgreSQL driver 提供的稳定 constraint name；不能解析包含用户值的完整错误
  文本。
- 只有 `DUPLICATE_SOURCE_SUFFIX` 可由后续应用/HTTP 层转换为
  `sources[i].url_suffix/DUPLICATE_SOURCE_SUFFIX`。其余已知冲突说明服务端生成 ID、Mapper 或
  聚合持久化流程违反不变量，不得伪装成用户输入错误。
- 未知 `IntegrityError` 在 rollback 后包装为不含底层文本的
  `CameraPersistenceOperationError`，并用异常链保留原始原因供内部诊断；Application Service
  不得依赖 SQLAlchemy 异常。后续公共依赖错误边界负责安全响应，日志和响应不得包含 SQL、
  参数、密码、完整 RTSP URL 或数据库约束名。

## 8. Fake、Fixture 与测试隔离

- 复用步骤 3 的固定 UUID、固定时钟和 `CameraBuilder`，补充单 Source、双 Source、十 Source
  以及列表分页数据 Builder。
- Fake Repository 与 Fake UoW 只能暴露第 2 节公共端口，不提供按 Row 修改、直接取 Store、
  强制插入损坏聚合等生产实现不存在的便利方法。
- Fake 使用一个测试显式创建的共享“已提交 Store”；每个 Fake UoW 初始化时取得独立工作
  副本。`add/save/delete` 只修改副本，`commit` 原子发布副本，`rollback` 丢弃副本并恢复到
  最新已提交状态。
- 一个 Fake UoW 的未提交写入对新建的其他 Fake UoW 不可见；commit 后新 UoW 可见，rollback
  后无残留。存入和读出聚合均使用不可变对象或安全副本，避免测试通过外部引用绕过事务。
- Fake 不模拟 PostgreSQL `FOR UPDATE`、阻塞、隔离级别、延迟约束或真实并发；这些只由真实
  PostgreSQL 测试证明。不得用 Fake 或 SQLite 推断生产并发行为。
- PostgreSQL 集成测试每例使用可回滚事务或独立 schema/database，不能依赖执行顺序。必须
  显式配置与应用库不同且名称以 `_test` 结尾的 `TEST_DATABASE_URL`。

## 9. 实施顺序

1. 定义 Repository/UoW Protocol、`CameraListCriteria` 和稳定持久化错误。
2. 实现领域聚合与 ORM Row 的显式双向 Mapper。
3. 将步骤 2 的 Row 级锁与引用校验收敛为内部能力，实现 `add/get` 和完整聚合读取。
4. 实现 `list/count` 的字面搜索、固定排序和分页。
5. 实现 `save/delete` 的锁内差异持久化和显式聚合删除。
6. 实现约束转换器与 SQLAlchemy UoW，覆盖 flush 和 commit 失败回滚。
7. 实现共享 Store、Fake Repository/Fake UoW 和 Fixture Builder。
8. 让 Fake 与 PostgreSQL 实现运行同一组 Repository contract tests，再补充 PostgreSQL 专属
   事务、约束与并发测试。

## 10. 必测场景

共享 Repository contract tests：

- 单 Source/多 Source round-trip 后 ID、时间、默认源、凭据和 Source 顺序不变。
- `add`、`get` 查无结果、`save` 全量新增/保留/删除/重排、`delete` 返回最新聚合行为一致。
- 名称/IP 大小写搜索、空搜索和 `%/_/\` 字面搜索一致；先搜索再 count。
- 分页固定为 `created_at ASC, camera_id ASC`，相同创建时间不跨页抖动，越界页返回空集合和
  真实 total。
- Fake 未 commit 对其他 UoW 不可见，commit 后可见，rollback 后无残留。

PostgreSQL 专属测试：

- add/save/delete 后不 commit 时其他事务不可见；rollback 后数据库无部分写入。
- Camera 删除先锁 Camera，再锁 Source，任一步骤失败时完整回滚，成功后无 Source 残留。
- 同一 Camera 规范化后缀竞态最终由延迟数据库约束阻止，并在 commit 边界转换为稳定 kind。
- Source 后缀和顺序可在完整更新中交换；未知约束不会被误映射。
- `for_update` 能串行化同一 Camera 的并发写意图；Camera 删除与 Source 写入后不产生孤儿。
- 直接构造的无 Source、默认源错误、断裂排序等损坏数据无法重建为看似合法的聚合。

UoW 与生命周期测试：

- `commit()` 成功持久化，commit 失败先 rollback 再抛出安全错误。
- 显式 `rollback()`、业务异常和任务取消均不残留写入。
- 正常退出依赖但未调用 commit 时不自动提交。
- 每个请求/任务获得独立 Session/UoW，且同一 Session 不被并发任务共享。
- Repository、UoW、异常文本和捕获日志不包含测试密码或完整 RTSP URL。

## 11. 退出条件与后续交接

- 后续业务 Service 只依赖 Repository/UoW Protocol 即可使用 Fake 编写单元测试。
- 所有聚合写操作都能在单事务成功或完整回滚；只有 UoW 可以 commit/rollback。
- Fake 与 PostgreSQL 实现通过同一组 Repository contract tests，PostgreSQL 专属事务和并发
  测试通过。
- Repository 不访问 MediaMTX、不构造 HTTP 响应、不记录凭据，也不向应用层返回 ORM Row。
- 本步骤不新增迁移；现有 ORM、无外键 DDL 和稳定约束名保持不变。
- 步骤 5/6 不直接依赖 SQLAlchemy；功能切片通过 FastAPI dependency 注入请求级 UoW。
  创建、更新和删除切片只能在数据库提交后执行 MediaMTX 尽力操作。
