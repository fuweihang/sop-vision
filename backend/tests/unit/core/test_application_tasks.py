"""应用入口导入和后台任务退出日志的单元测试。"""

import asyncio
import importlib
import logging

import pytest

import app.factory as factory_module

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
    # 让刚创建的任务进入失败状态，测试不会依赖真实时间或轮询等待。
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
    # 同一事件循环轮次即可稳定完成两个无等待协程，不引入基于时长的等待。
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
