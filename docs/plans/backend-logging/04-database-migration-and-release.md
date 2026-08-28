# 04｜SQLAlchemy/Alembic 接入、文档和全量验证

## 任务目标

让 SQLAlchemy SQL 调试输出和 Alembic 迁移日志使用统一格式，避免 `echo=True` 与根 Handler 重复；
补齐配置、安全和兼容性文档，并完成 Backend 全量验证。

## 当前上下文 / 前置条件

- 必须先完成任务 1–3，并阅读同目录 `README.md` 的全局规则。
- `DATABASE_ECHO` 是已有公开环境变量，需要保持兼容，不能无说明删除。
- Runtime Engine 当前始终启用 `hide_parameters=True`。
- Alembic 集成测试会在 pytest 进程内多次加载 `migrations/env.py`。
- 迁移日志初始化不能移除 pytest、caplog 或已存在的应用 Handler。
- HTTP 中间件顺序和 Uvicorn access 去重已经在任务 3 固定，本任务只做回归验证。

## 实施范围

修改：

- `backend/src/app/core/database/engine.py`
- `backend/src/app/core/logging.py`
- `backend/src/app/server.py`
- `backend/migrations/env.py`
- `backend/alembic.ini`
- `backend/tests/core/database/test_engine.py`
- `backend/tests/core/database/test_migrations.py`
- `backend/tests/core/test_logging.py`
- `backend/tests/test_server.py`
- `backend/README.md`
- `.env.example`
- `backend/.env.local.example`
- `docs/modules/cameras/foundation.md`
- `docs/modules/cameras/stream-gateway.md`
- `docs/modules/cameras/media-reconciliation.md`

## 明确不做

- 不记录 SQL 参数或数据库 URL。
- 不修改连接池、事务、迁移内容或数据库 Schema。
- 不引入新的日志库、采集服务或指标系统。
- 不修改 `backend/scripts/` 中作为 CLI 成功结果的 `print()`。
- 不删除或重命名 `DATABASE_ECHO`。
- 不重新设计任务 1–3 已交付的日志格式、业务事件或 HTTP access 行为。

## 实施步骤

1. 保留 `DATABASE_ECHO` 对外含义，但改变内部实现：
   - Runtime Engine 始终传 `echo=False`，避免 SQLAlchemy 自行调用 `basicConfig()` 或添加输出。
   - `app.server` 把 `database_echo` 传给统一日志配置；`true` 时
     `sqlalchemy.engine=INFO`，`false` 时 `sqlalchemy=WARNING`，与总览级别表一致。
   - `BACKEND_LOG_LEVEL=debug` 不得绕过上述规则开启 SQL、httpx 或 httpcore 细节。
   - `hide_parameters=True` 始终保持。
2. SQLAlchemy 继续使用 `database.sql` 组件，不展开私有 record 字段。SQL 文本仍是 message，但 console
   通过任务 1 Formatter 转义换行，JSON 保持一条记录一个对象。
3. Alembic 不再通过 `fileConfig()` 安装另一套 Formatter：
   - 独立 CLI 进程没有根 Handler 时，安装一个与 Runtime 相同的统一 `stderr` Handler，并使用
     `database.migration` 组件。
   - pytest/应用进程已有 Handler 时，不新增、替换或删除任何 Handler，只调整 Alembic 和数据库
     Logger 级别；由宿主决定 Formatter，避免破坏 caplog。迁移开始前保存这些 Logger 的显式级别，
     在 offline/online 成功、失败和取消的 `finally` 中恢复，不能污染同一 pytest/应用进程的后续日志。
   - 保持 `disable_existing_loggers=False` 的效果。
4. 精简 `alembic.ini` 日志段，保留 Alembic 必需的非日志配置。
5. 更新 Engine 测试，明确断言 `echo=False` 和 `hide_parameters=True`。
6. 增加 SQL 参数和数据库密码泄漏测试，覆盖 console 与 JSON。
   增加 Alembic 在“独立进程无 Handler”和“pytest 已有 Handler”两种情况下的安装次数、级别和
   Handler 保留测试，并断言迁移结束后宿主 Logger 级别恢复。
7. 更新 README、环境变量示例和设计文档：
   - 默认格式与级别。
   - `BACKEND_LOG_FORMAT` 用法。
   - `BACKEND_LOG_LEVEL` 优先于兼容变量 `UVICORN_LOG_LEVEL`，后者只作为未设置新变量时的回退。
   - `DATABASE_ECHO` 通过统一 Logger 输出。
   - 持续故障、恢复和 HTTP access 规则。
8. 执行 Backend 全量检查并人工检查 Compose 启动输出。

## 验证方式

```bash
cd backend
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run python scripts/check_mediamtx_contract.py
uv run python scripts/check_camera_placeholders.py foundation
cd ..
docker compose config
```

配置独立 `TEST_DATABASE_URL` 后额外执行：

```bash
cd backend
uv run --env-file .env.local pytest \
  tests/core/database/test_migrations.py \
  tests/modules/cameras/test_repository.py \
  tests/modules/cameras/test_reconciliation_persistence.py
```

人工检查：

- `DATABASE_ECHO=false` 时不打印 SQL。
- `DATABASE_ECHO=true` 时 SQL 使用统一前缀、每条只打印一次、参数始终隐藏。
- `alembic current/upgrade` 使用统一时间、级别和组件格式。
- Backend 启动、HTTP 请求、对账失败、持续提醒、恢复和停止日志符合总览示例。

## 完成标准

- SQLAlchemy 和 Alembic 不再输出另一套格式。
- `DATABASE_ECHO=true` 不产生重复 SQL 日志，凭据和参数不泄漏。
- 所有 Backend 单元测试、静态检查和可用的 PostgreSQL 集成测试通过。
- README、环境变量示例和设计文档与实际行为一致。
- 变更说明明确日志文本兼容性：外部系统不得继续按整行 `operation=... outcome=...` 解析，
  应启用 JSON 并读取 `event` 与稳定字段。

## 与下一任务的衔接信息

本任务是日志重设计的最终交付。完成后记录：

- 全量验证命令和结果，包括因缺少 `TEST_DATABASE_URL` 跳过的项目。
- 最终环境变量、启动命令和示例输出。
- 需要同步更新的外部日志采集规则。
- 仍未接入日志平台时，JSON 输出的启用方式。

后续如接入日志平台，应基于现有 JSON 输出增加部署侧采集，不应重新修改业务 Logger 或放宽字段
白名单。
