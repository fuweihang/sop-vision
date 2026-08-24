"""DatabaseRuntime 的 Session 隔离、事务防御和 factory 配置测试。"""

from unittest.mock import AsyncMock, Mock

import pytest

from app.core.config import Settings
from app.core.database.session import DatabaseRuntime, create_database_runtime

pytestmark = pytest.mark.anyio


async def test_session_is_closed_without_implicit_commit() -> None:
    """正常退出只关闭 Session，不替 Unit of Work 提交或回滚。"""

    session = AsyncMock()
    runtime = DatabaseRuntime(AsyncMock(), Mock(return_value=session))  # type: ignore[arg-type]

    async with runtime.session() as yielded_session:
        assert yielded_session is session

    session.close.assert_awaited_once_with()
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()


async def test_session_rolls_back_and_closes_on_exception() -> None:
    """异常退出先防御性回滚，再关闭 Session 并保留原始异常。"""

    session = AsyncMock()
    runtime = DatabaseRuntime(AsyncMock(), Mock(return_value=session))  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="会话失败"):
        async with runtime.session():
            raise RuntimeError("会话失败")

    session.rollback.assert_awaited_once_with()
    session.close.assert_awaited_once_with()


async def test_each_context_gets_an_independent_session() -> None:
    """每次上下文调用 factory，禁止在请求或任务之间共享 Session。"""

    first_session = AsyncMock()
    second_session = AsyncMock()
    session_factory = Mock(side_effect=[first_session, second_session])
    runtime = DatabaseRuntime(AsyncMock(), session_factory)  # type: ignore[arg-type]

    async with runtime.session() as yielded_first:
        pass
    async with runtime.session() as yielded_second:
        pass

    assert yielded_first is first_session
    assert yielded_second is second_session
    assert yielded_first is not yielded_second


async def test_runtime_factory_disables_implicit_flush() -> None:
    """factory 禁用 autoflush，并避免 commit 后 ORM 属性被隐式过期。"""

    settings = Settings()
    engine = AsyncMock()

    with pytest.MonkeyPatch.context() as monkeypatch:
        create_engine = Mock(return_value=engine)
        session_factory = Mock()
        monkeypatch.setattr(
            "app.core.database.session.create_database_engine",
            create_engine,
        )
        monkeypatch.setattr(
            "app.core.database.session.async_sessionmaker",
            session_factory,
        )

        runtime = create_database_runtime(settings)

    assert runtime.engine is engine
    session_factory.assert_called_once_with(
        engine,
        autoflush=False,
        expire_on_commit=False,
    )
