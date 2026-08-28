"""Alembic 异步迁移环境，复用应用 metadata 与数据库配置。"""

import asyncio

from alembic import context
from sqlalchemy import Connection, make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.database import Base
from app.core.logging import migration_logging_context
from app.modules.cameras.persistence import models as camera_models  # noqa: F401

config = context.config

# 后续 ORM 表统一挂到此 metadata，autogenerate 才能看到完整应用 Schema。
target_metadata = Base.metadata


def get_database_url() -> str:
    """优先使用测试注入 URL，否则读取应用 SecretStr 的原始值。

    ``Config.attributes`` 不会写回 alembic.ini，因此迁移测试可安全指向临时数据库，
    而不会把凭据持久化到仓库。类型检查用于尽早拒绝意外传入的复杂配置对象。
    """

    override = config.attributes.get("database_url")
    if override is not None:
        if not isinstance(override, str):
            raise TypeError("Alembic database_url 覆盖值必须是字符串")
        return override
    return get_settings().database_url.get_secret_value()


def run_migrations_offline() -> None:
    """不建立连接即可生成离线 SQL，并复用同一 metadata。"""

    context.configure(
        url=make_url(get_database_url()),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """在 Alembic 提供的同步桥接连接内执行实际 revision 链。"""

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """用 NullPool 执行一次迁移，并在成功或失败后显式 dispose Engine。

    迁移进程是短生命周期命令，不应复用 Web 应用的常驻连接池；连接超时仍沿用应用配置，
    ``hide_parameters`` 则防止迁移异常输出 SQL 参数。
    """

    settings = get_settings()
    connectable = create_async_engine(
        get_database_url(),
        connect_args={"connect_timeout": settings.database_connect_timeout},
        hide_parameters=True,
        poolclass=NullPool,
    )
    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    """从 Alembic 同步入口启动一次独立 asyncio 事件循环。"""

    asyncio.run(run_async_migrations())


# Alembic 的默认模板会从 alembic.ini 调用 fileConfig()，这会在嵌入式命令中替换 pytest 或应用
# 已有的 Handler。本项目改由统一 logging 模块管理：独立 CLI 安装统一格式，嵌入进程只临时调整
# Logger 级别，并在下方 with 的 finally 路径恢复。
settings = get_settings()
with migration_logging_context(
    log_format=settings.backend_log_format,
    database_echo=settings.database_echo,
):
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()
