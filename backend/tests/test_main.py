"""应用工厂与 lifespan 数据库资源清理测试。"""

import asyncio
import importlib
import logging

import pytest

import app.factory as factory_module
from app.core.config import Settings
from app.core.database import DatabaseRuntime
from app.factory import ReconciliationTaskRunner
from app.main import create_app
from app.modules.stream_gateway.ports import StreamGatewayPort

pytestmark = pytest.mark.anyio


def test_importing_main_does_not_replace_host_logging_handlers() -> None:
    """OpenAPI、pytest 等普通导入 app.main 时不得触发进程级日志重配。"""

    import app.main

    root = logging.getLogger()
    handler = logging.NullHandler()
    root.addHandler(handler)
    try:
        importlib.reload(app.main)
        assert handler in root.handlers
    finally:
        root.removeHandler(handler)


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
            self.dependencies_open_when_stopped = (
                not self.runtime.disposed and not self.stream_gateway._client.is_closed  # type: ignore[attr-defined]
            )


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


class TimeoutAwaitableTask:
    """只覆盖停止函数的 timeout 分支，不等待真实五秒。"""

    def cancel(self) -> None:
        """保持与 asyncio.Task 相同的窄调用形状。"""

    def __await__(self):
        """模拟等待后台任务时由 timeout 上下文报告超时。"""

        async def raise_timeout() -> None:
            raise TimeoutError

        return raise_timeout().__await__()


async def test_reconciliation_shutdown_timeout_uses_stable_event(caplog) -> None:
    """停止超时只记录固定 outcome 和时限，不附加伪造异常栈。"""

    with caplog.at_level(logging.ERROR, logger="app.factory"):
        await factory_module._stop_reconciliation_task(  # type: ignore[arg-type]
            TimeoutAwaitableTask()
        )

    record = next(record for record in caplog.records if record.name == "app.factory")
    assert record.message == "媒体对账任务停止异常"
    assert record.event == "media_reconciliation.runner_exit"
    assert record.outcome == "shutdown_timeout"
    assert record.timeout_seconds == 5
    assert not hasattr(record, "error_type")


async def test_reconciliation_task_error_logs_only_safe_exception_fields(caplog) -> None:
    """停止等待捕获的未知异常只留下 helper 生成的类型和帧，不记录异常文本。"""

    sentinel = "runner-exception-secret"

    async def fail() -> None:
        raise RuntimeError(sentinel)

    task = asyncio.create_task(fail())
    await asyncio.sleep(0)
    with caplog.at_level(logging.ERROR, logger="app.factory"):
        await factory_module._stop_reconciliation_task(task)

    record = next(record for record in caplog.records if record.name == "app.factory")
    assert record.outcome == "shutdown_error"
    assert record.error_type == "RuntimeError"
    assert record.error_frames
    assert all(isinstance(frame, str) for frame in record.error_frames)
    assert record.exc_info is None
    assert sentinel not in caplog.text


async def test_reconciliation_done_callback_distinguishes_crash_and_normal_exit(caplog) -> None:
    """done callback 报告崩溃安全帧，正常意外退出不制造空异常字段。"""

    async def fail() -> None:
        raise ValueError("done-callback-secret")

    async def finish() -> None:
        return None

    failed_task = asyncio.create_task(fail())
    finished_task = asyncio.create_task(finish())
    await asyncio.sleep(0)
    caplog.clear()
    with caplog.at_level(logging.ERROR, logger="app.factory"):
        factory_module._report_reconciliation_task_exit(failed_task)
        factory_module._report_reconciliation_task_exit(finished_task)

    records = [record for record in caplog.records if record.name == "app.factory"]
    assert [record.outcome for record in records] == ["crashed", "unexpected_exit"]
    assert records[0].error_type == "ValueError"
    assert records[0].error_frames
    assert records[0].exc_info is None
    assert not hasattr(records[1], "error_type")
    assert "done-callback-secret" not in caplog.text
