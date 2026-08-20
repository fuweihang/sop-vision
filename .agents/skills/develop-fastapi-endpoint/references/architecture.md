# FastAPI 分层与实现规范

## 目录

- [1. 项目适配](#1-项目适配)
- [2. Router 与 API](#2-router-与-api)
- [3. API Schema](#3-api-schema)
- [4. 调用者与权限](#4-调用者与权限)
- [5. 依赖注入与生命周期](#5-依赖注入与生命周期)
- [6. Application Service](#6-application-service)
- [7. Domain 与 Port](#7-domain-与-port)
- [8. Repository 与 Mapper](#8-repository-与-mapper)
- [9. 事务与 Unit of Work](#9-事务与-unit-of-work)
- [10. 并发与幂等](#10-并发与幂等)
- [11. ORM、数据库与迁移](#11-orm数据库与迁移)
- [12. 异常与错误协议](#12-异常与错误协议)
- [13. 外部 Adapter](#13-外部-adapter)
- [14. Lifespan 与后台任务](#14-lifespan-与后台任务)
- [15. 安全与敏感数据](#15-安全与敏感数据)
- [16. 可观测性](#16-可观测性)
- [17. 测试分层](#17-测试分层)
- [18. 开发与生产运行](#18-开发与生产运行)

## 1. 项目适配

先识别目标仓库真实结构，不预设 `src` 布局、同步或异步 SQLAlchemy、API 版本、错误格式或认证方式。

重点确认：

- 应用工厂或 `FastAPI` 实例的位置。
- 路由聚合和版本前缀。
- 配置来源与依赖注入方式。
- 请求级和应用级资源的生命周期。
- 数据库、迁移和事务基础设施是否已经存在。
- 前端、SDK、OpenAPI 与功能文档是否构成外部契约。

优先扩展相邻模块已经验证的模式。若现有模式存在明显风险，只在任务范围内修正并说明兼容性影响。

## 2. Router 与 API

Router 负责：

- HTTP 方法、路径、参数和依赖声明。
- 调用应用层用例。
- 将应用输出转换为响应。
- 声明成功与错误响应的 OpenAPI 信息。

Router 不负责：

- SQL、ORM Record 操作或事务提交。
- 跨 Repository 的业务编排。
- 可复用的权限和领域规则。
- 捕获宽泛 `Exception` 后返回成功或底层错误。

Path ID 在全链路保持真实类型，例如始终使用 `UUID`。`204` 不返回响应体。每个公开操作使用稳定 `operation_id`，避免生成客户端无意义变化。

## 3. API Schema

按不同语义拆分 Create、Update/Patch、Detail、List Item 和分页响应。不要为减少文件数量而复用含义不同的模型。

规则：

- 显式限制长度、范围、格式和枚举。
- 根据项目策略决定未知字段是拒绝还是忽略。
- PATCH 区分未提供与显式 `null`。
- API Schema、应用 DTO 和 ORM Record 保持独立。
- 响应只公开调用方需要的字段。
- 字段别名、命名风格、时间和 UUID 格式与既有契约一致。

输入语法校验留在 Schema；跨字段、资源状态和数据库相关规则进入应用层或领域层。

## 4. 调用者与权限

认证边界应把 JWT、Session 或上游身份转换为稳定、最小的调用者对象。Service 不自行解析 Token，也不依赖框架 Request。

资源所有权、租户和软删除条件应进入查询：

```python
statement = select(Record).where(
    Record.id == resource_id,
    Record.tenant_id == actor.tenant_id,
    Record.deleted_at.is_(None),
)
```

不要先按 ID 获取全部资源，再在 Python 中检查归属。无权限是返回 `403` 还是按不存在处理为 `404`，遵循项目已冻结的防枚举策略。

## 5. 依赖注入与生命周期

Composition Root 可以同时知道接口和具体实现，业务层不应自行构造数据库 Session 或第三方客户端。

要求：

- 每个请求拥有独立请求状态和数据库 Session。
- 同一用例的 Repository 与 UoW 共享 Session。
- HTTP 客户端、连接池等长生命周期资源由 lifespan 创建和关闭。
- 依赖提供器可被测试覆盖。
- 全局单例不保存请求级状态。

若项目使用应用工厂，测试应创建隔离应用，避免跨测试污染 `dependency_overrides` 或 `app.state`。

## 6. Application Service

Service 表达业务用例，负责权限、不变量、状态转换、多个 Port 的编排和事务边界。

Service 不应：

- 依赖 FastAPI Request/Response 或抛出 `HTTPException`。
- 包含 SQLAlchemy `select()`、`update()` 等基础设施查询。
- 返回未约束的第三方字典或 ORM Record。
- 捕获所有异常并降级为成功。

只转换能够准确解释的异常，并保留异常链。外部依赖是否允许降级必须来自业务契约，而不是为了让接口看似可用。

## 7. Domain 与 Port

只有出现以下需求时才增加领域对象或独立 Port：

- 规则被多个用例复用。
- 存在复杂状态转换或关键不变量。
- 外部系统或 Repository 需要可替换。
- Service 测试需要稳定 Fake。
- 具体依赖导致循环引用或难以测试。

使用 `Protocol` 定义应用层真正需要的最小能力。不要把整个 SDK、数据库客户端或万能 BaseRepository 暴露给 Service。

## 8. Repository 与 Mapper

Repository 负责查询、投影、ORM 创建和修改、所有权过滤及原子条件更新。

Repository 可以 `add()`、`flush()`，必要时 `refresh()`；不得 `commit()`、抛 `HTTPException` 或依赖 API Schema。

列表查询应具备：

- 明确数量上限。
- 稳定排序和确定的次排序键。
- 与数据规模匹配的分页策略。
- 避免 N+1 和不必要的大字段读取。

Mapper 显式完成 API Request、应用输入、ORM Record、应用输出和 API Response 之间的转换，避免隐式序列化泄露字段。

## 9. 事务与 Unit of Work

一个业务用例对应一个可见事务边界：

- Router 不管理事务。
- Repository 不提交或回滚。
- 所有数据库写入共享一个 Session/UoW。
- 未处理异常导致回滚。
- `commit()` 失败后正确回滚。
- 只读用例不做无意义提交。

外部网络调用通常放在事务外。若业务要求数据库与远程系统一致，明确采用提交后操作、Outbox、Saga、补偿或可重试任务；普通数据库事务不能回滚远程副作用。

## 10. 并发与幂等

以下流程不能保证并发正确：

```text
查询不存在 → 创建
查询状态可用 → 更新
查询没有运行任务 → 启动任务
```

根据场景选择：

- 唯一约束与冲突处理。
- `INSERT ... ON CONFLICT`。
- `UPDATE ... WHERE state = ... RETURNING`。
- 乐观锁/version 字段。
- `SELECT ... FOR UPDATE`。
- advisory lock 或跨实例租约。
- 持久化幂等键。

进程内锁只约束单进程。必须明确多 worker、多实例、重试和客户端断线后的行为。

## 11. ORM、数据库与迁移

如果项目采用 SQLAlchemy 2.x，优先使用类型化 ORM：

```python
class Record(Base):
    id: Mapped[UUID] = mapped_column(primary_key=True)
```

显式审查主键、nullable、长度、默认值、外键、唯一/check 约束、索引、时区、软删除和版本字段。

索引从真实的 WHERE、JOIN、ORDER BY 和分页方式推导。唯一性、幂等和关键状态约束优先由数据库保证。

若项目使用 Alembic：

- ORM 变化必须有迁移。
- 审查自动生成内容，不直接信任生成结果。
- 处理旧数据回填和约束建立顺序。
- 验证空数据库升级与现有版本升级。
- 不用应用启动时的 `create_all()` 替代版本化迁移。
- 不把第三方自管表误纳入迁移。

项目尚无 ORM 或迁移设施时，不因 skill 自行引入；先确认任务确实需要，并同步锁文件、配置、文档和测试。

## 12. 异常与错误协议

业务异常使用稳定类型，HTTP 层集中映射状态码和错误模型。项目采用 Problem Details 时，保持正确内容类型以及稳定 `type/status/code/trace_id` 等字段。

错误响应不得包含：

- SQL、堆栈和连接信息。
- 密码、Token 和凭据 URL。
- 第三方原始敏感响应。
- 调用方不需要的内部 ID 或状态。

OpenAPI 声明必须与真实异常一致。不要把依赖故障一律映射为 `500`，也不要把失败伪装成空成功响应。

## 13. 外部 Adapter

HTTP API、消息系统、缓存、对象存储、媒体服务和推理服务均视为 Adapter。

Adapter 负责：

- 内外部类型转换。
- 连接、读取和总超时。
- 仅对安全操作执行有限重试。
- 第三方异常到稳定应用异常的转换。
- 降级值和敏感信息过滤。

Service 不依赖第三方 SDK 的响应结构。测试通过 Fake 或协议级 Mock 覆盖成功、超时、无效响应和部分故障。

## 14. Lifespan 与后台任务

使用 FastAPI lifespan 管理应用级资源：连接池、共享异步客户端、订阅器和后台消费者。初始化部分失败时，明确应用是否应拒绝启动还是以降级模式运行。

后台任务必须具备：

- 可控启动与取消。
- 异常上报，不能静默退出。
- 关闭时限和资源回收。
- 多 worker 下的单例或多实例语义。
- 重连、背压和消息丢失策略。

不要在每个请求中重复创建昂贵客户端，也不要把一次请求拥有的对象泄露给后台任务。

## 15. 安全与敏感数据

默认不在日志、错误、指标标签或缓存中保存 Secret、密码、Token、连接串和完整带凭据 URL。

如果产品契约要求 API 返回敏感字段：

- 严格执行鉴权与授权。
- 使用项目规定的 `Cache-Control` 等响应头。
- 确保访问日志、异常追踪和校验错误不回显。
- 限制其出现的响应模型和接口范围。

不得凭通用最佳实践擅自改变已批准的产品协议；发现风险时清晰报告并寻求决策。

## 16. 可观测性

按项目规则记录 request/trace ID、操作名、允许记录的调用者或资源 ID、耗时及稳定失败类型。

避免记录完整请求体、完整响应体和高基数或敏感字段。外部调用应可区分超时、连接失败、无效响应和业务拒绝，但日志不泄露原始凭据。

## 17. 测试分层

### Service 单元测试

使用类型匹配的 Fake 测试业务流程、权限、状态转换、异常和事务意图。

### Repository 集成测试

使用目标数据库验证 SQL、约束、软删除、原子更新和并发。不要用 SQLite 推断 PostgreSQL 特性。

### API 契约测试

通过应用工厂或依赖覆盖验证请求、状态码、错误协议、响应字段、响应头、鉴权和 OpenAPI。

### Adapter 测试

模拟协议边界，验证超时、重试、降级、异常转换和敏感数据过滤。

### 迁移测试

覆盖空库升级、旧版本升级、数据回填、约束和必要的回滚路径。

## 18. 开发与生产运行

保留项目已经工作的启动方式。常见开发入口包括 `fastapi dev` 或显式 Uvicorn import string 加 `--reload`；`src` 布局可能还需要项目已有的工作目录、`--app-dir` 或入口配置。

开发模式要求：

- 自动重载只用于本地开发。
- 环境文件、端口和绑定地址沿用项目约定。
- 热更新命令与容器生产命令分离。
- 生产环境不使用 `--reload`。

改变入口前先核对当前 FastAPI CLI 官方文档、部署方式、Dockerfile、Compose、IDE 和 README，避免制造两套相互漂移的命令。
