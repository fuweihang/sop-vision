# 步骤 2｜关系模型与无外键约束迁移

> 前置：[步骤 1](./01-database-runtime.md)  
> 产出：`cameras`、`camera_sources` 表、可自动验证的数据库约束及应用层引用完整性方案

## 1. 完成目标

把 Foundation 已冻结的 Camera 聚合不变量落实为 PostgreSQL DDL 和 Repository 事务规则。表之间不创建外键；数据库负责单表内可可靠表达的完整性，跨表引用、显式级联删除和连续排序等规则由应用层负责。

## 2. 表与约束

### `cameras`

- `camera_id uuid primary key`，无客户端或数据库自增语义。
- `name varchar(128) not null`。
- `ip_address inet not null`，并以 `CHECK family(ip_address) = 4` 保证持久化层也拒绝 IPv6。
- `rtsp_port integer not null`，`CHECK 1 <= rtsp_port AND rtsp_port <= 65535`。
- `username varchar(128) not null`。
- `password varchar(512) not null`；当前 MVP 按既定语义保存，日志和 ORM `repr` 必须排除。
- `default_preview_source_id uuid not null`。
- `created_at/updated_at timestamptz not null`。

### `camera_sources`

- `source_id uuid primary key`。
- `camera_id uuid not null`，仅作为应用层维护的逻辑引用，不创建外键。
- `name varchar(128) not null`。
- `url_suffix varchar(1024) COLLATE "C" not null`，固定大小写敏感比较语义，不依赖数据库默认 collation。
- `sort_order integer not null`，`CHECK sort_order >= 0`。
- `created_at/updated_at timestamptz not null`。
- `UNIQUE (camera_id, url_suffix) DEFERRABLE INITIALLY DEFERRED`，允许一次完整聚合更新中安全交换两个 Source 的后缀。
- `UNIQUE (camera_id, sort_order) DEFERRABLE INITIALLY DEFERRED`，既防止重复位置，也允许事务内重排。
- `INDEX (camera_id)`，支持按 Camera 查询、加锁校验和显式删除 Source。

### 跨表引用完整性替代方案

不为 `camera_sources.camera_id` 或 `cameras.default_preview_source_id` 创建外键。Repository 必须通过同一数据库事务、稳定的加锁顺序和显式校验维护以下不变量：

- 新增或更新 Source 前，先以 `SELECT ... FOR UPDATE` 锁定并确认对应 Camera 存在。
- 创建 Camera 聚合时，先插入 Camera 和全部 Source，再确认默认源存在且其 `camera_id` 等于当前 Camera，最后提交事务。
- 更新默认源时，先锁定 Camera，再锁定目标 Source，并校验二者的 `camera_id` 一致。
- 删除 Source 时，先锁定 Camera；若目标是当前默认源，必须在同一事务内先切换到另一条同 Camera Source，且禁止删除最后一路 Source。
- 删除 Camera 时，先锁定 Camera，显式删除其全部 Source，再删除 Camera，所有操作在同一事务内完成。
- 同一 Camera 的写入和删除均先锁定 Camera，使 Source 新增与 Camera 删除串行化，避免产生孤儿记录。

所有生产写入必须经过 Repository，禁止业务代码直接操作这两张表。另提供可重复执行的完整性巡检查询，检测 Source 无父 Camera、默认源不存在、默认源属于其他 Camera、Camera 无 Source 四类异常；巡检发现异常时告警，不自动删除或修改数据。

## 3. 数据库与领域职责边界

数据库负责：

- UUID 列类型和主键；两张表之间不创建任何外键。
- 同 Camera 后缀唯一、排序位置唯一。
- 端口和非负排序的数值范围。
- 为应用层引用校验和显式删除提供必要索引。

领域层负责：

- UUID 必须为服务端生成的 v4。
- trim、URL 后缀去前导 `/`、字符串非空。
- `sort_order` 从 0 开始连续。
- Source 引用的 Camera 存在。
- 默认源存在、属于同一 Camera，且每个已提交 Camera 至少有一路 Source。
- 删除 Camera 时在同一事务内显式删除其全部 Source。
- 在写库前提供精确的字段错误。

数据库约束和索引名称必须稳定，供后续 Repository/Unit of Work 将竞态下的 IntegrityError 转为业务错误并支持巡检；API 不得返回约束名。无外键意味着直接 SQL 可以绕过跨表不变量，因此 Repository 事务测试和生产巡检均为必需项，不能以调用方自律替代。

## 4. 实施顺序

1. 定义 metadata/ORM table，先不加入 Repository 行为。
2. 生成迁移后人工审阅 UUID、时区、约束名、索引和 downgrade 顺序，并确认 DDL 不包含 `FOREIGN KEY` 或 `REFERENCES`。
3. 在空 PostgreSQL 上升级并检查实际 DDL。
4. 实现 Repository 的事务锁、跨表校验和显式删除行为。
5. 编写单表数据库约束测试、Repository 并发测试和完整性巡检测试。
6. 验证从步骤 1 基线升级、回滚到基线、再次升级。

## 5. 必测场景

- 插入合法的单 Source 和多 Source 聚合。
- Camera ID、Source ID 主键重复被拒绝。
- 通过 Repository 写入不存在的 Camera、把默认源设为不存在或属于另一 Camera 的 Source 时提交失败。
- Camera 删除时，Repository 在同一事务内删除所有 Source；任一步骤失败时整体回滚。
- Source 新增与 Camera 删除并发执行后，不产生孤儿 Source。
- 默认源更新与 Source 删除并发执行后，默认源仍存在且属于同一 Camera。
- 同 Camera 重复 `url_suffix` 被拒绝；不同 Camera 可使用相同后缀。
- `ABC` 与 `abc` 可作为同一 Camera 的两个不同后缀。
- 重复 `sort_order`、负数排序和越界端口被拒绝。
- 完整性巡检能识别四类跨表异常，且只告警、不自动修复。
- 迁移 `upgrade → downgrade → upgrade` 后约束仍一致。

## 6. 退出条件

- 空库升级和上一版本升级测试均通过。
- 两张表的实际 DDL 不包含外键或 `REFERENCES`。
- 聚合默认源不变量由 Repository 事务校验和并发测试保证。
- 删除 Camera 的显式级联行为由 PostgreSQL Repository 集成测试证明。
- 完整性巡检查询及其告警接入方式已经确定并有自动化测试。
- 迁移不包含运行时状态、WHEP、完整 RTSP URL 或未来业务字段。

## 7. 后续交接

向步骤 4 提供稳定表结构、约束名、索引名和完整性巡检查询。后续 Repository 必须遵循“先锁 Camera，再锁 Source”的顺序，在单事务内完成引用校验、聚合写入和显式删除；任何调用方不得假设数据库外键会兜底。
