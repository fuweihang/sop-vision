# Cameras Foundation 执行计划

> 需求事实源：[Foundation 契约](../README.md)
>
> 执行方式：步骤 1–9 严格顺序；每步可单独提交和验收

## 当前基线

| 步骤              | 状态   | 代码证据                                                              |
| ----------------- | ------ | --------------------------------------------------------------------- |
| 1 数据库运行时    | 已完成 | `app/core/database/`、Alembic 基线、生命周期与迁移测试                |
| 2 关系模型        | 已完成 | Camera 无外键 DDL、稳定约束、巡检与 PostgreSQL 测试                   |
| 3 领域模型        | 已完成 | 不可变聚合、规范化、固定 ID/时钟与领域测试                            |
| 4 Repository/UoW  | 已完成 | 专用端口、SQLAlchemy/Fake 实现、事务与并发测试                        |
| 5 HTTP 公共机制   | 已完成 | trace、Problem、严格 UUID、分页依赖及 probe 测试                      |
| 6 OpenAPI 契约    | 已完成 | Cameras Schema/占位 Router、确定性导出脚本与 `contracts/openapi.json` |
| 7 前端 Client     | 已完成 | operation 生成类型、单一 Axios Client、Problem 映射与固定 Query Key   |
| 8 前端状态与 Mock | 未开始 | 有通用 Route State/MSW 基础，尚无 Cameras 场景集合                    |
| 9 契约门禁        | 未开始 | 尚无 regenerate-and-diff 和占位清理门禁                               |

代码检查结果：不加载本地数据库配置时 Backend 为 `110 passed, 13 skipped`；加载
`.env.local` 后，PostgreSQL 迁移、约束、事务和并发测试全部执行，为 `123 passed`。测试
fixture 显式固定 CORS Origin；即使进程传入冲突的 `BACKEND_CORS_ORIGINS`，HTTP Foundation
定向测试仍为 `27 passed`。

步骤 7 完成后 Frontend 为 `83 passed`，lint、format check 和生产 build 全部通过；
`pnpm api:generate` 可从已提交 OpenAPI 直接重建 operation 类型，无需手工补丁。

## 架构边界

```text
HTTP Schema / dependency
          ↓
Cameras application ports
          ↓
     Cameras domain
          ↑
SQLAlchemy repository / UoW

OpenAPI → generated frontend types → Client / MSW
```

- `app/modules/cameras/` 拥有 Camera 聚合、持久化端口/适配器和 Cameras HTTP Schema。
- `app/modules/stream_gateway/` 只拥有 MediaMTX 运行时能力，不拥有 Camera 配置模型。
- `app/core/database/` 和 `app/core/http/` 只提供跨模块基础设施。
- `contracts/` 保存确定性生成的跨端 OpenAPI 产物。
- 不建立 Generic Repository、全能 Base Service 或只服务占位阶段的抽象。

## 步骤 1｜数据库运行时（已完成）

产物：

- 必填、脱敏的 `DATABASE_URL` 和连接池配置。
- 惰性 AsyncEngine、独立 AsyncSession factory、lifespan dispose。
- Alembic metadata 接线和不含业务 DDL 的基线 revision。
- 只接受独立 `*_test` 数据库的迁移测试。

验收：Session 无隐式 commit；异常 rollback；`upgrade head → downgrade base → upgrade head`；
日志和异常不含数据库密码。

## 步骤 2｜关系模型（已完成）

产物：

- `cameras` 与 `camera_sources` 表，无任何外键。
- 原生 UUID/INET/timestamptz；IPv4、端口、非负顺序 CHECK。
- `(camera_id, url_suffix)` 与 `(camera_id, sort_order)` 延迟唯一约束及 Camera 索引。
- 四类跨表引用完整性巡检，只告警不修复。

本步骤只拥有表、约束、索引、迁移和巡检；Repository 行为、锁与并发由步骤 4 所有。

验收：实际 PostgreSQL DDL、升级/回滚、大小写敏感后缀、延迟约束和无外键检查通过。

## 步骤 3｜领域模型（已完成）

产物：

- 框架无关、不可变的 `Camera/CameraSource` 聚合。
- 创建、重建、完整更新、默认源切换和 RTSP URL 派生。
- UUID/Clock 端口、生产实现、固定测试实现和 Builder。
- 稳定字段错误和聚合损坏错误；Secret 默认输出脱敏。

验收：字段规范化、聚合不变量、Source ID/创建时间保留、连续顺序、损坏数据拒绝及敏感输出
测试通过；领域测试不启动 FastAPI、PostgreSQL 或 MediaMTX。

## 步骤 4｜Repository 与 UoW（已完成）

产物：

- `CameraRepository.add/save/get/list/count/delete` 和 `CameraUnitOfWork` Protocol。
- 显式领域/ORM Mapper、SQLAlchemy 实现、Fake Store/UoW 和共享 contract tests。
- Camera → Source 固定锁顺序、完整集合差异更新、显式删除和约束错误转换。
- 名称/IP 字面搜索、固定排序、分页和批量 Source 读取。

验收：Fake 与 PostgreSQL 共享契约通过；提交/回滚可见性、延迟约束、并发保存/删除、损坏数据
和敏感错误边界由真实 PostgreSQL 测试证明。

## 步骤 5｜HTTP 公共机制（已完成）

产物：

- ASGI trace middleware、ContextVar 和日志 Filter；成功/错误/CORS 响应均有同源 ID。
- RFC 9457 风格 Problem/FieldError 与框架、领域、数据库异常转换。
- canonical UUID v4 类型、嵌套字段路径转换、分页和搜索依赖。
- 仅存在于测试的 probe router；无 Camera CRUD handler。

验收：标准 `uv run --env-file .env.local pytest` 运行全部 107 项且无失败/跳过；冲突 CORS
环境不会改变测试应用；请求原始 input、数据库错误、密码和完整 RTSP URL 不进入 Problem
或日志。

## 步骤 6｜Schema、占位 Router 与 OpenAPI（已完成）

建立唯一的后端 HTTP Schema 来源：

- `CameraCreateRequest/CameraUpdateRequest` 及 Source item。
- `CameraDetail/CameraSourceDetail`、`CameraSummary/CameraPage`。
- 默认源变更、状态摘要、PlaybackInfo 和公共 Problem response。
- 请求模型 `extra="forbid"`；列表与 Playback Schema 通过黑名单测试禁止敏感字段。

目标响应矩阵：列表 `200/422/503`；创建 `201/422/503`；详情 `200/404/422/500/503`；更新
`200/404/422/503`；默认源 `200/404/422/503`；删除 `204/404/422/503`；Playback
`200/404/409/422/502/503`。Cameras 只使用 `cameras`、`camera-sources` tag；现有健康检查保留
`healthLiveness/healthReadiness` operation ID，readiness 的 `503` 引用公共 Problem。

在真实应用注册全部目标路径和稳定 operation ID。未实现 handler 的函数体只能直接
`raise NotImplementedError`：不装配 Service/Repository，不定义占位错误协议，也不建立第二个
契约应用。OpenAPI 只描述目标成功和业务错误，路径存在不代表业务已可调用。

生成 `contracts/openapi.json` 时不进入 lifespan、不连接依赖；固定元数据、排序、缩进和换行，
连续生成必须字节一致。创建 `201` 声明 Location/no-store，详情和更新声明 no-store，Playback
`409` 声明 Retry-After，所有响应声明 X-Trace-Id。顶层请求/响应使用经 Schema 校验的固定
example；只有 CameraDetail example 可以包含明确标记的测试凭据和完整测试 RTSP URL。

退出条件：删除或迁移早期单流 Camera Schema；七条业务路径的 Schema、响应头、媒体类型和
operation ID 结构测试通过；调用占位接口的临时结果不进入正式契约。

## 步骤 7｜前端类型、Client 与错误映射（已完成）

建立 `pnpm api:generate`，使用固定依赖从 `contracts/openapi.json` 确定性生成包含
`paths/components/operations` 的 `frontend/src/generated/openapi.ts`；生成文件不进入 lint/format，
但仍由 TypeScript build 检查，业务代码只从 operation 索引请求、查询和响应类型。

保留唯一生产 Axios 实例并提供七个 Cameras operation 调用。响应错误在 Client 边界立即脱敏：
只有媒体类型、Problem Schema、HTTP status 和 `X-Trace-Id` 全部一致才公开业务
`status/code/errors/context`；传输失败和非 Problem 响应不携带业务 code、原始请求配置或响应体，
占位 Backend 的临时错误不会形成业务分支。

字段错误解析器把 `sources[1].name` 转换为 `['sources', 1, 'name']`，畸形路径降级为表单级错误。
Query Key 只提供 `cameras/camera/playback` 三种冻结形状，列表 HTTP 参数与 Key 共用 q trim、空值、
默认分页规范化，且无 sort 维度。当前 Query cache 仅驻留内存；安全回归测试证明 Camera 写请求断网
后，密码哨兵不进入抛出错误、console、localStorage 或 sessionStorage。

退出条件：重新生成后无需手工补丁，Frontend build/lint/test 通过；占位 Backend 的临时错误
不产生前端分支。

## 步骤 8｜页面状态基元与 MSW

- 复用设计系统实现首次加载、后台刷新、空数据、搜索无结果和可恢复错误组合基元。
- 使用生成类型建立固定 UUID/时间的 Cameras Fixture Builder 和显式 MSW 场景。
- 覆盖成功、嵌套 `422`、`404/409/502/503`、首次失败和后台刷新失败。
- 每例重置 handler/计数器；未处理请求直接失败，绝不访问真实 Backend/MediaMTX。

退出条件：后续切片可选择场景独立开发；公共基元不内置具体 CRUD；Frontend 全套检查通过。

## 步骤 9｜契约门禁与交接

CI 顺序：Backend 检查 → PostgreSQL 迁移/Repository 测试 → 导出 OpenAPI → 生成 TS →
工作区漂移检查 → Frontend 检查 → 敏感数据专项测试。

门禁必须发现字段/必填性/类型/枚举、operation ID、错误响应和媒体类型漂移，并阻止列表或
Playback 新增敏感字段。使用唯一 leak sentinel 覆盖领域、Pydantic、SQLAlchemy、Problem、
日志、生成物、MSW 非详情响应和浏览器存储。

Foundation 收口时允许七个 handler 仍是一行 `raise NotImplementedError`；MVP 发布门禁则要求
它们已被对应功能切片原位替换。每个功能切片替换 handler 时必须同步重新生成 OpenAPI、前端
类型和 Fixture，并增加运行时行为测试。

## 统一交付要求

- 每步包含实现、与风险匹配的测试、必要命令说明和公共契约变更说明。
- 当前步骤未通过定向测试和受影响工程完整检查前，不进入下一步。
- Foundation 不实现 Camera CRUD、MediaMTX 状态/播放、鉴权、Redis、WebSocket 或可靠清理。
- 不修改生成的 `frontend/src/routeTree.gen.ts`；不把真实凭据写入文档、日志、快照或产物。

当前通用验收命令：

```bash
cd backend
uv run python scripts/export_openapi.py
uv run --env-file .env.local pytest
uv run ruff check .
uv run ruff format --check .

cd ../frontend
pnpm api:generate
pnpm test
pnpm lint
pnpm format:check
pnpm build
```

步骤 6–9 新增的 OpenAPI 导出、类型生成和漂移检查必须提供稳定脚本，并加入上述完整门禁；
不得依赖开发者手工记忆命令。
