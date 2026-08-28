"""根据应用配置构造进程级异步 SQLAlchemy Engine。"""

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings


def create_database_engine(settings: Settings) -> AsyncEngine:
    """创建惰性连接 Engine；构造阶段不会主动访问 PostgreSQL。

    ``hide_parameters`` 始终开启，语句绑定参数不会进入日志或 ``StatementError`` 文本。
    ``echo`` 固定关闭，因为 SQL 调试输出已经由统一 logging 配置控制；若在这里再次启用，
    SQLAlchemy 可能自行安装输出 Handler，导致同一条 SQL 重复打印。连接池的实际关闭由
    FastAPI lifespan 负责。
    """

    return create_async_engine(
        settings.database_url.get_secret_value(),
        connect_args={"connect_timeout": settings.database_connect_timeout},
        echo=False,
        hide_parameters=True,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,
        pool_recycle=settings.database_pool_recycle,
        pool_size=settings.database_pool_size,
        pool_timeout=settings.database_pool_timeout,
    )
