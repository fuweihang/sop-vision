"""由守护进程以 ``spawn`` 模式调用的通用 Worker 进程入口。"""

from __future__ import annotations

import logging
from multiprocessing.connection import Connection
from typing import Any, Protocol

LOGGER = logging.getLogger(__name__)


class StopEvent(Protocol):
    def is_set(self) -> bool: ...

    def set(self) -> None: ...

    def wait(self, timeout: float | None = None) -> bool: ...


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
