"""应用工厂与 lifespan 数据库资源清理测试。"""

import pytest

from app.core.config import Settings
from app.main import create_app

pytestmark = pytest.mark.anyio


class StubDatabaseRuntime:
    """只实现 lifespan 所需 dispose 协议的轻量测试替身。"""

    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        """记录关闭调用，避免测试创建真实 SQLAlchemy Engine。"""

        self.disposed = True


async def test_lifespan_disposes_injected_database_runtime(settings: Settings) -> None:
    """应用退出 lifespan 后必须关闭由工厂注入的数据库 Runtime。"""

    runtime = StubDatabaseRuntime()
    application = create_app(
        settings=settings,
        # 该替身只实现 lifespan 实际使用的 dispose 能力，无需伪造 Session factory。
        database_runtime_factory=lambda _settings: runtime,  # type: ignore[arg-type]
    )

    async with application.router.lifespan_context(application):
        assert application.state.database_runtime is runtime
        assert not runtime.disposed

    assert runtime.disposed
