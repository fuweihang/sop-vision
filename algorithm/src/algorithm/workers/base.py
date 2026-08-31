"""由守护进程以 ``spawn`` 模式调用的通用 Worker 进程入口。"""

from __future__ import annotations

import logging
import signal
import threading
from multiprocessing.connection import Connection
from typing import Any, Protocol

LOGGER = logging.getLogger(__name__)


class StopEvent(Protocol):
    def is_set(self) -> bool: ...

    def set(self) -> None: ...

    def wait(self, timeout: float | None = None) -> bool: ...


def install_stop_signal_handlers(
    stop: StopEvent,
) -> dict[signal.Signals, signal.Handlers]:
    """让独立 Worker 在收到 SIGINT/SIGTERM 时走正常资源清理流程。

    Python 只允许主线程注册信号处理器，因此测试或嵌入线程调用时直接跳过。
    返回原处理器供退出阶段恢复，避免直接运行 Worker 时污染宿主进程状态。
    """

    previous: dict[signal.Signals, signal.Handlers] = {}

    def request_stop(_signum: int, _frame: object) -> None:
        stop.set()

    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.getsignal(signum)
            signal.signal(signum, request_stop)
    return previous


def restore_signal_handlers(
    previous: dict[signal.Signals, signal.Handlers],
) -> None:
    """恢复 :func:`install_stop_signal_handlers` 替换前的处理器。"""

    for signum, handler in previous.items():
        signal.signal(signum, handler)


def worker_process_main(
    worker_type: str,
    task_id: str,
    config_payload: dict[str, Any],
    stop_event: StopEvent,
    status_sender: Connection,
) -> None:
    """重建已验证配置，执行注册入口，并通过 Pipe 报告就绪或错误。"""

    from algorithm.daemon.registry import get_worker_definition

    def report(state: str, detail: str | None = None) -> None:
        message = {"state": state}
        if detail is not None:
            message["detail"] = detail
        try:
            status_sender.send(message)
        except (BrokenPipeError, EOFError, OSError):
            pass

    report("starting")
    try:
        definition = get_worker_definition(worker_type)
        config = definition.config_model.model_validate(config_payload)
        definition.entrypoint(
            config,
            stop_event=stop_event,
            ready_callback=lambda: report("running"),
        )
    except BaseException as error:
        report("error", f"{type(error).__name__}: {error}")
        LOGGER.exception("Worker %s failed", task_id)
        raise
    finally:
        status_sender.close()
