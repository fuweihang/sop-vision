"""应用工厂 lifespan 的资源启动与关闭顺序测试。"""

import asyncio

import pytest

from app.core.config import Settings
from app.core.database import DatabaseRuntime
from app.factory import ReconciliationTaskRunner
from app.main import create_app
from app.modules.stream_gateway.ports import StreamGatewayPort

pytestmark = pytest.mark.anyio


class StubDatabaseRuntime:
    """只实现 lifespan 所需 dispose 协议的轻量测试替身。"""

    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        """记录关闭调用，避免测试创建真实 SQLAlchemy Engine。"""

        self.disposed = True


class OrderingReconciliationRunner:
    """记录取消时依赖资源状态，验证 lifespan 的真实关闭顺序。"""

    def __init__(self, runtime: StubDatabaseRuntime, stream_gateway: StreamGatewayPort) -> None:
        self.runtime = runtime
        self.stream_gateway = stream_gateway
        self.started = False
        self.stopped = False
        self.dependencies_open_when_stopped = False

    async def run_forever(self) -> None:
        """等待取消，并在 finally 中观察 HTTP Client 和数据库是否仍可用。"""

        self.started = True
        try:
            await asyncio.Event().wait()
        finally:
            self.stopped = True
            # Port 不公开生命周期状态；此处只在 composition root 测试里观察 Adapter 的 client。
            client_is_closed = self.stream_gateway._client.is_closed  # type: ignore[attr-defined]
            self.dependencies_open_when_stopped = not self.runtime.disposed and not client_is_closed


async def test_lifespan_disposes_injected_database_runtime(settings: Settings) -> None:
    """应用退出 lifespan 后必须关闭数据库 Runtime 与共享 Stream Gateway Adapter。"""

    runtime = StubDatabaseRuntime()
    runner_holder: list[OrderingReconciliationRunner] = []

    def runner_factory(
        _settings: Settings,
        _runtime: DatabaseRuntime,
        stream_gateway: StreamGatewayPort,
    ) -> ReconciliationTaskRunner:
        runner = OrderingReconciliationRunner(runtime, stream_gateway)
        runner_holder.append(runner)
        return runner

    application = create_app(
        settings=settings,
        # 该替身只实现 lifespan 实际使用的 dispose 能力，无需伪造 Session factory。
        database_runtime_factory=lambda _settings: runtime,  # type: ignore[arg-type]
        media_reconciliation_runner_factory=runner_factory,
    )

    async with application.router.lifespan_context(application):
        # 让 create_task 至少进入一次 Runner；启动本身不等待首次对账完成。
        await asyncio.sleep(0)
        assert application.state.database_runtime is runtime
        assert not runtime.disposed
        stream_gateway = application.state.stream_gateway
        # Port 不公开实现生命周期状态；这里检查私有 client 只为证明 composition root 确实
        # 把 Adapter 注册进 AsyncExitStack，并不把该属性作为业务可依赖接口。
        assert not stream_gateway._client.is_closed
        assert runner_holder[0].started

    assert runtime.disposed
    assert stream_gateway._client.is_closed
    assert runner_holder[0].stopped
    assert runner_holder[0].dependencies_open_when_stopped
