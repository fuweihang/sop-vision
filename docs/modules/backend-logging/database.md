# 数据库与迁移日志

## Runtime SQL

Runtime AsyncEngine 固定使用 `echo=False` 和 `hide_parameters=True`。`DATABASE_ECHO` 不直接传给
SQLAlchemy `echo`，而是控制统一配置中的 `sqlalchemy.engine` Logger：

- `DATABASE_ECHO=true`：Logger 为 INFO，终端能看到 `database.sql` SQL 日志。
- `DATABASE_ECHO=false`：Logger 为 WARNING，普通 SQL 不显示；SQLAlchemy WARNING/ERROR 仍可能显示。
- `BACKEND_LOG_LEVEL=debug` 不会打开 SQL，也不会打开连接池、httpx 或 httpcore 的详细日志。

环境变量改变后必须重启 Backend 进程或容器。console 和 JSON 使用同一个 Handler，因此不会因为
同时启用 SQLAlchemy echo 和 root logging 而重复输出。

`hide_parameters=True` 会把绑定参数显示为
`[SQL parameters hidden due to hide_parameters=True]`，也会避免 `StatementError` 文本回显参数。它不能
隐藏直接拼进 SQL 文本的秘密；密码、Token 和其他敏感值必须使用绑定参数，禁止字符串拼接。

## Alembic

`alembic.ini` 不拥有独立的 logger、handler 或 formatter 配置，迁移环境也不调用 `fileConfig()`。

- 独立运行 `alembic current/upgrade` 时，如果 root 没有 Handler，迁移环境安装一个与 Runtime 相同的
  stderr Handler，使用 `database.migration` 和可选的 `database.sql` 组件。
- pytest 或应用进程内调用 Alembic 时，保留宿主已有 Handler，只在迁移期间调整 Alembic 与
  SQLAlchemy Logger 级别。
- 迁移成功、失败或取消后恢复原 Logger 级别；独立 CLI 的 Handler 保留到短生命周期进程退出，
  同一进程重复执行命令也不会重复安装。

迁移读取同一组 `BACKEND_LOG_FORMAT` 与 `DATABASE_ECHO` 配置。数据库 URL 使用 Secret 保存，配置
校验失败、迁移异常和日志均不得回显密码或完整连接串。

## 排障与验证

日常交付在仓库根目录运行 `./scripts/verify-changed.sh`。以下命令只用于检查 Alembic 当前状态、打开
SQL 排障输出，或单独复验 PostgreSQL 迁移环境：

```bash
cd backend
uv run --env-file .env.local alembic current
DATABASE_ECHO=true uv run --env-file .env.local alembic current
uv run --env-file .env.local pytest tests/unit/core/test_logging.py \
  tests/unit/core/database/test_engine.py \
  tests/integration/core/test_migrations.py
```

`tests/integration/core/test_migrations.py` 的 PostgreSQL 路径要求独立、尚不存在且名称以 `_test`
结尾的 `TEST_DATABASE_URL`。未配置时集成测试会明确失败，避免把未验证误报为通过。
