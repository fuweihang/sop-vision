# 步骤 2｜关系模型与约束迁移

> 前置：[步骤 1](./01-database-runtime.md)  
> 产出：`cameras`、`camera_sources` 表及可自动验证的数据库约束

## 1. 完成目标

把 Foundation 已冻结的 Camera 聚合不变量落实为 PostgreSQL DDL。数据库负责可可靠表达的完整性，连续排序等跨行规则仍由领域层负责。

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
- `camera_id uuid not null`，删除 Camera 时 `ON DELETE CASCADE`。
- `name varchar(128) not null`。
- `url_suffix varchar(1024) COLLATE "C" not null`，固定大小写敏感比较语义，不依赖数据库默认 collation。
- `sort_order integer not null`，`CHECK sort_order >= 0`。
- `created_at/updated_at timestamptz not null`。
- `UNIQUE (camera_id, url_suffix) DEFERRABLE INITIALLY DEFERRED`，允许一次完整聚合更新中安全交换两个 Source 的后缀。
- `UNIQUE (camera_id, sort_order) DEFERRABLE INITIALLY DEFERRED`，既防止重复位置，也允许事务内重排。
- 为复合外键提供 `UNIQUE (camera_id, source_id)`。

### 同聚合默认源

用复合外键表达“默认源属于当前 Camera”：

```text
cameras(camera_id, default_preview_source_id)
    → camera_sources(camera_id, source_id)
```

该外键必须是 `DEFERRABLE INITIALLY DEFERRED`。迁移先创建两张表，再添加复合外键；回滚时先删除复合外键，以正确处理循环依赖。默认源非空且复合外键存在，也同时保证已提交 Camera 至少有一路 Source。

## 3. 数据库与领域职责边界

数据库负责：

- UUID 列类型、主键、外键、级联删除。
- 同 Camera 后缀唯一、排序位置唯一。
- 端口和非负排序的数值范围。
- 默认源实际存在且属于同一 Camera。

领域层负责：

- UUID 必须为服务端生成的 v4。
- trim、URL 后缀去前导 `/`、字符串非空。
- `sort_order` 从 0 开始连续。
- 在写库前提供精确的字段错误。

数据库约束名称必须稳定，供 Repository 将竞态下的 IntegrityError 转为业务错误；API 不得返回约束名。

## 4. 实施顺序

1. 定义 metadata/ORM table，先不加入 Repository 行为。
2. 生成迁移后人工审阅 UUID、时区、外键、约束名和 downgrade 顺序。
3. 在空 PostgreSQL 上升级并检查实际 DDL。
4. 编写直接 SQL/Session 约束测试。
5. 验证从步骤 1 基线升级、回滚到基线、再次升级。

## 5. 必测场景

- 插入合法的单 Source 和多 Source 聚合。
- Camera ID、Source ID 主键重复被拒绝。
- 默认源不存在或属于另一 Camera 时提交失败。
- Camera 删除时所有 Source 数据库级联删除。
- 同 Camera 重复 `url_suffix` 被拒绝；不同 Camera 可使用相同后缀。
- `ABC` 与 `abc` 可作为同一 Camera 的两个不同后缀。
- 重复 `sort_order`、负数排序和越界端口被拒绝。
- 迁移 `upgrade → downgrade → upgrade` 后约束仍一致。

## 6. 退出条件

- 空库升级和上一版本升级测试均通过。
- 聚合默认源由数据库约束保证，不仅依赖应用检查。
- 删除 Camera 的级联行为由 PostgreSQL 集成测试证明。
- 迁移不包含运行时状态、WHEP、完整 RTSP URL 或未来业务字段。

## 7. 后续交接

向步骤 4 提供稳定表结构和约束名。后续 Repository 必须在单事务内写入循环依赖数据，并在提交前满足延迟复合外键。
