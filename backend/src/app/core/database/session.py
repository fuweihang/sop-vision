"""请求/任务级 AsyncSession 生命周期及 FastAPI 依赖装配。"""

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.database.engine import create_database_engine


class DatabaseRuntime:
    """封装共享 Engine 和只负责创建独立 Session 的 factory。

    Runtime 是应用级资源，但它不保存任何请求状态；每次调用 ``session()`` 都会获得一个
    新 ``AsyncSession``。业务提交仍由后续 Unit of Work 控制，此处绝不隐式 commit。
    """

    def __init__(
        self,
        engine: AsyncEngine,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.engine = engine
        self.session_factory = session_factory

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession]:
        """提供单次使用的 Session，并在所有退出路径释放底层连接。

        未处理异常（包括任务取消）先执行防御性 rollback，确保连接返回池前不保留失败
        事务；正常路径只 close，不替业务层提交或回滚事务。
        """

        session = self.session_factory()
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def dispose(self) -> None:
        """关闭连接池中所有已归还连接；由应用 lifespan 在关闭阶段调用。"""

        await self.engine.dispose()


def create_database_runtime(settings: Settings) -> DatabaseRuntime:
    """从 Settings 组装 Engine 与无隐式 flush/过期行为的 Session factory。"""

    engine = create_database_engine(settings)
    session_factory = async_sessionmaker(
        engine,
        autoflush=False,
        expire_on_commit=False,
    )
    return DatabaseRuntime(engine, session_factory)


def get_database_runtime(request: Request) -> DatabaseRuntime:
    """从当前应用实例取 Runtime，避免依赖模块级 Engine 单例。"""

    return request.app.state.database_runtime


async def get_database_session(
    runtime: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
) -> AsyncIterator[AsyncSession]:
    """仅在声明此依赖的请求中创建 Session，并保证请求结束后关闭。"""

    async with runtime.session() as session:
        yield session
