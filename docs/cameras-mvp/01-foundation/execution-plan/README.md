# Cameras Foundation 顺序执行计划

> 来源：[01｜Cameras 基础契约](../README.md)  
> 执行方式：按顺序实施，不要求并行  
> 计划粒度：每一步均可单独指派、提交、回滚和验收

## 1. 拆分目标

Foundation 同时包含持久化、领域、HTTP、契约和前端基础设施。如果一次性交付，数据库约束、错误语义和生成类型会在末期才发生集成冲突。本计划按依赖方向拆分，使每一步都满足以下条件：

- 只有一个主要架构关注点。
- 明确消费的前置产物和向后续提供的接口。
- 不依赖尚未实现的 Camera 业务路由即可测试。
- 通过自动化验收后即可合并，不以“后续再补测试”为完成条件。
- 失败时可以回滚当前步骤，而不推翻之前已经冻结的契约。

“可独立执行”不表示步骤彼此无依赖，而是指执行者只需读取本步骤、Foundation 事实源和列明的前置产物，就可以完成实现与验收。

## 2. 已知仓库基线

- Backend 已有 FastAPI 应用工厂和 `stream_gateway` 模块，但尚无 SQLAlchemy、Alembic 或 Camera 持久化实现。
- 现有 `stream_gateway/schemas/camera.py` 是早期单流占位契约，与 Cameras MVP 聚合模型不一致，不能继续作为事实源。
- Frontend 已有 Axios、TanStack Query、MSW、Camera 路由骨架和通用 Route State 组件，但尚无 OpenAPI 生成链路或 Cameras Query Key。
- Compose 已提供 PostgreSQL 17；数据库集成测试应使用 PostgreSQL，不用 SQLite 模拟 UUID、延迟唯一约束、行锁或排序约束。
- Foundation 期间不新增 `POST/GET/PUT/PATCH/DELETE` Camera 业务路由。

## 3. 架构边界

### 3.1 模块所有权

- `app/modules/cameras/`：Camera 聚合、领域规则、持久化端口、ORM 映射和 Cameras HTTP Schema。
- `app/modules/stream_gateway/`：MediaMTX 适配器及运行时媒体能力；不再拥有 Camera 配置模型。
- `app/core/database/`：Engine、Session、Alembic 接线等进程级数据库基础设施。
- `app/core/http/`：Problem Details、trace ID 和框架异常转换等跨模块 HTTP 机制。
- `contracts/`：可复现生成的 OpenAPI 跨端契约。

不要建立跨所有业务的 Generic Repository 或全能 Base Service。Foundation 只定义 Cameras MVP 已确认消费者需要的端口。

### 3.2 依赖方向

```text
HTTP Schema / API dependency
            ↓
    Cameras application ports
            ↓
       Cameras domain
            ↑
SQLAlchemy repository / Unit of Work

OpenAPI artifact → generated frontend types → API client / MSW
```

领域层不得导入 FastAPI、Pydantic、SQLAlchemy、Axios 或 MediaMTX 类型。外部依赖错误必须在适配器或 HTTP 边界转换，不能渗入领域对象。

## 4. 执行顺序

| 顺序 | 步骤 | 独立交付结果 | 主要后续消费者 |
| --- | --- | --- | --- |
| 1 | [数据库运行时与迁移骨架](./01-database-runtime.md) | 可配置、可释放、可迁移的 PostgreSQL 接线 | 步骤 2、4 |
| 2 | [关系模型与约束迁移](./02-relational-schema.md) | `cameras/camera_sources` 表、约束、升级与回滚测试 | 步骤 4 |
| 3 | [领域模型与规范化规则](./03-domain-model.md) | 与框架无关的 Camera 聚合和值规则 | 步骤 4、6 |
| 4 | [Repository 与事务边界](./04-repository-uow.md) | 可原子保存和读取聚合的持久化端口及实现 | 功能切片 02–09 |
| 5 | [HTTP 公共机制](./05-http-foundation.md) | trace ID、Problem Details、严格 UUID、分页查询 | 步骤 6、功能路由 |
| 6 | [公共 Schema 与 OpenAPI](./06-openapi-contract.md) | 可复现的 Cameras 契约文件和后端 Schema 测试 | 步骤 7、8 |
| 7 | [前端类型、Client 与错误映射](./07-frontend-client.md) | 唯一类型来源、API 错误解析和 Query Key | 功能页面、步骤 8 |
| 8 | [前端状态基元与 Mock Server](./08-frontend-mocks.md) | 可切换的成功/失败场景与共享页面状态 | 功能切片 02–09 |
| 9 | [契约门禁与 Foundation 收口](./09-contract-gates.md) | CI 漂移检测、安全回归和交接说明 | 所有后续切片 |

默认采用严格顺序。即使团队具备并行能力，也应至少等当前步骤的公共接口和自动化验收合并后再开始下一步，避免重复定义契约。

## 5. 每步统一交付要求

每个步骤的 PR 或提交必须包含：

1. 本步骤代码、配置和迁移文件。
2. 与风险匹配的单元测试或 PostgreSQL 集成测试。
3. 受影响的启动、生成或测试命令说明。
4. 对已冻结公共接口的变更说明；无变更也要明确写“无”。
5. 不包含后续步骤或业务切片的占位实现。

每步验收先运行该步骤列出的定向测试，再运行受影响工程的完整 lint/test。只要本步骤的退出条件未满足，就不进入下一步。

## 6. 全局非目标

- 不实现 Camera 创建、列表、详情、更新、默认源切换、播放或删除路由。
- 不访问真实摄像头，不要求 MediaMTX 在线。
- 不引入鉴权、RBAC、WebSocket、Redis、审计或可靠异步清理。
- 不把密码、完整 RTSP URL 或敏感响应写入日志、快照、生成产物或浏览器持久化存储。
- 不修改生成的 `frontend/src/routeTree.gen.ts`。

## 7. Foundation 完成判定

步骤 1–9 全部完成后，后续任一 Cameras 功能切片都应能直接复用以下产物：

- PostgreSQL 迁移与真实约束。
- Camera 聚合、Repository、Unit of Work、固定 ID/时钟 Fixture。
- 统一 Problem Details、严格 UUID、分页与 trace ID。
- 可复现 OpenAPI、前端生成类型、API Client、Query Key 和字段错误映射。
- MSW 场景入口和加载/刷新/空/失败状态基元。
- CI 中的迁移、契约漂移与敏感数据回归门禁。

此时仍然没有 Camera 业务 API 或完成态页面；第一个业务能力由 `02-camera-create` 负责。
