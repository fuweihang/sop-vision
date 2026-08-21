# 步骤 1｜数据库运行时与迁移骨架

> 前置：无  
> 产出：SQLAlchemy/Alembic 基础设施可连接 PostgreSQL、执行空迁移链并安全释放资源

## 1. 完成目标

为 Backend 建立最小数据库运行时，但不创建任何 Cameras 业务表。本步骤只解决配置、连接生命周期、Session 边界和迁移命令是否可靠。

## 2. 实现范围

- 增加 SQLAlchemy 2.x async、Alembic 和 PostgreSQL 驱动，并同步更新锁文件。
- 将 `DATABASE_URL` 纳入 Settings；配置对象和日志的 `repr` 不得暴露密码。
- 采用明确的 SQLAlchemy 驱动 URL，例如 `postgresql+psycopg://...`，同步 `.env.example` 和 Compose 默认值。
- 在 `app/core/database/` 提供 Engine/Session factory；模块导入时不得主动连接数据库。
- 通过 FastAPI lifespan 释放 Engine；每次请求或任务获得独立 `AsyncSession`。
- 初始化 Alembic，确保迁移环境复用应用的 metadata 和数据库配置。
- 提供不含业务 DDL 的基线迁移，证明 upgrade/downgrade 链路可执行。

建议文件边界：

```text
backend/
├── alembic.ini
├── migrations/
│   ├── env.py
│   └── versions/
└── src/app/core/database/
    ├── engine.py
    └── session.py
```

## 3. 关键设计约束

- 不在全局创建永不释放的 Session。
- Repository 决定 flush，Unit of Work 决定 commit/rollback；请求依赖不得隐式提交。
- 测试可替换 Engine/Session factory，不能依赖修改进程全局单例。
- 连接池、SQL echo 和超时均从配置读取；生产默认不输出 SQL 参数。
- 数据库故障在本步骤只验证资源释放，不提前定义业务 `503` 映射。
- 不把 PostgreSQL 健康检查并入现有 MediaMTX readiness；通用健康语义不在 Foundation 范围。

## 4. 实施顺序

1. 添加依赖并更新 `uv.lock`。
2. 扩展 Settings 和环境样例，增加 URL 脱敏测试。
3. 实现 Engine/Session factory 及 lifespan dispose。
4. 初始化 Alembic 配置和 metadata 入口。
5. 建立基线迁移并在空数据库上运行 upgrade/downgrade。
6. 补充 Backend README 中的迁移命令。

## 5. 自动化验证

- Settings 能读取合法 URL，缺失或非法配置有确定失败。
- 测试中创建的 Session 结束后必定关闭，异常路径触发 rollback。
- 应用 lifespan 结束时调用 Engine dispose。
- PostgreSQL 空库可执行 `upgrade head → downgrade base → upgrade head`。
- 捕获的配置日志和异常文本不包含测试数据库密码。

建议验收命令：

```bash
cd backend
uv run alembic upgrade head
uv run alembic downgrade base
uv run pytest tests/core/database tests/test_config.py
uv run ruff check .
uv run ruff format --check .
```

## 6. 退出条件

- 从全新 PostgreSQL 数据库可重复完成迁移和回滚。
- FastAPI 测试生命周期结束后没有未关闭连接告警。
- 本步骤没有 Camera ORM、Repository 或业务表。
- 数据库凭据不出现在日志、测试快照和异常响应中。

## 7. 后续交接

向步骤 2 提供稳定的 metadata 与 Alembic 入口；向步骤 4 提供可注入的 Session factory。后续步骤不得绕过这些入口自行创建 Engine。
