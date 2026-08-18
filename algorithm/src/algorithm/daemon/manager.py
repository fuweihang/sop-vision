"""AIWorker 子进程的同步命令管理器。"""

from __future__ import annotations

import logging
import multiprocessing
import threading
import time
from dataclasses import dataclass
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any

from algorithm.workers.base import worker_process_main

from .config_loader import ConfigLoadError, LoadedWorker, load_config
from .models import CommandName, CommandResponse, RuntimeState

LOGGER = logging.getLogger(__name__)


class WorkerManagerError(RuntimeError):
    pass


class WorkerNotFoundError(WorkerManagerError):
    pass


class WorkerBusyError(WorkerManagerError):
    pass


class WorkerStartError(WorkerManagerError):
    pass


class WorkerStartTimeout(WorkerManagerError):
    pass


class WorkerStopError(WorkerManagerError):
    pass


@dataclass(slots=True)
class WorkerRecord:
    loaded: LoadedWorker
    process: Any | None = None
    stop_event: Any | None = None
    status_receiver: Connection | None = None
    runtime_state: RuntimeState = RuntimeState.STOPPED
    last_error: str | None = None


class WorkerManager:
    """按 task_id 串行执行 start/reload/restart/stop。"""

    def __init__(
        self,
        config_path: Path,
        *,
        startup_timeout: float = 60.0,
        graceful_stop_timeout: float = 10.0,
        terminate_timeout: float = 3.0,
        process_context: Any | None = None,
    ) -> None:
        self.config_path = config_path.expanduser().resolve()
        self.startup_timeout = startup_timeout
        self.graceful_stop_timeout = graceful_stop_timeout
        self.terminate_timeout = terminate_timeout
        self._context = process_context or multiprocessing.get_context("spawn")
        self._records: dict[str, WorkerRecord] = {}
        self._records_lock = threading.Lock()
        self._task_locks: dict[str, threading.Lock] = {}
        self._closing = threading.Event()

        # Fail fast, but deliberately do not cache or autostart workers here.
        load_config(self.config_path)

        self._monitor = threading.Thread(
            target=self._monitor_processes,
            name="worker-process-monitor",
            daemon=True,
        )
        self._monitor.start()

    def start(self, task_id: str) -> CommandResponse:
        with self._command_lock(task_id):
            record = self._get_record(task_id)
            if record is not None and self._is_alive(record):
                return self._response(record, CommandName.START)
            if record is not None:
                self._stop_record(record)

            loaded = self._load_task(task_id, clear_missing=True)
            record = self._replace_loaded(record, loaded)
            return self._spawn_and_wait(record, CommandName.START)

    def reload(self, task_id: str) -> CommandResponse:
        with self._command_lock(task_id):
            record = self._get_record(task_id)
            forced = self._stop_record(record) if record is not None else False
            try:
                loaded = self._load_task(task_id, clear_missing=True)
            except (ConfigLoadError, WorkerNotFoundError):
                # Invalid files retain the old validated record; a valid file that
                # removed the task is handled by _load_task(clear_missing=True).
                raise
            record = self._replace_loaded(record, loaded)
            response = self._spawn_and_wait(record, CommandName.RELOAD)
            return response.model_copy(update={"forced_stop": forced})

    def restart(self, task_id: str) -> CommandResponse:
        with self._command_lock(task_id):
            record = self._get_record(task_id)
            if record is None:
                raise WorkerNotFoundError(
                    f"worker {task_id!r} has no successfully loaded configuration"
                )
            forced = self._stop_record(record)
            response = self._spawn_and_wait(record, CommandName.RESTART)
            return response.model_copy(update={"forced_stop": forced})

    def stop(self, task_id: str) -> CommandResponse:
        with self._command_lock(task_id):
            record = self._get_record(task_id)
            if record is None:
                raise WorkerNotFoundError(
                    f"worker {task_id!r} has no successfully loaded configuration"
                )
            forced = self._stop_record(record)
            response = self._response(record, CommandName.STOP)
            return response.model_copy(update={"forced_stop": forced})

    def config_is_readable(self) -> bool:
        try:
            load_config(self.config_path)
        except ConfigLoadError:
            return False
        return True

    def close(self) -> None:
        if self._closing.is_set():
            return
        self._closing.set()
        with self._records_lock:
            records = list(self._records.values())
        for record in records:
            if record.stop_event is not None:
                record.stop_event.set()
        for record in records:
            try:
                self._stop_record(record)
            except WorkerStopError:
                LOGGER.exception("Could not stop Worker %s", record.loaded.task_id)
        self._monitor.join(timeout=2.0)

    def _load_task(self, task_id: str, *, clear_missing: bool) -> LoadedWorker:
        try:
            configuration = load_config(self.config_path)
        except ConfigLoadError:
            LOGGER.error(
                "Could not load local algorithm configuration at %s",
                self.config_path,
            )
            raise
        loaded = configuration.workers.get(task_id)
        if loaded is None:
            if clear_missing:
                with self._records_lock:
                    self._records.pop(task_id, None)
            raise WorkerNotFoundError(f"worker {task_id!r} is not in config.json")
        return loaded

    def _replace_loaded(
        self,
        record: WorkerRecord | None,
        loaded: LoadedWorker,
    ) -> WorkerRecord:
        if record is None:
            record = WorkerRecord(loaded=loaded)
        else:
            record.loaded = loaded
            record.last_error = None
        with self._records_lock:
            self._records[loaded.task_id] = record
        return record

    def _spawn_and_wait(
        self,
        record: WorkerRecord,
        command: CommandName,
    ) -> CommandResponse:
        receiver, sender = self._context.Pipe(duplex=False)
        stop_event = self._context.Event()
        process = self._context.Process(
            target=worker_process_main,
            args=(
                record.loaded.worker_type,
                record.loaded.task_id,
                record.loaded.config.model_dump(mode="json"),
                stop_event,
                sender,
            ),
            name=f"aiworker-{record.loaded.task_id}",
            daemon=False,
        )
        record.process = process
        record.stop_event = stop_event
        record.status_receiver = receiver
        record.runtime_state = RuntimeState.STARTING
        record.last_error = None

        try:
            process.start()
        except Exception as error:
            receiver.close()
            record.runtime_state = RuntimeState.FAILED
            record.last_error = f"{type(error).__name__}: {error}"
            record.process = None
            record.stop_event = None
            record.status_receiver = None
            raise WorkerStartError(
                f"worker {record.loaded.task_id!r} failed to start"
            ) from error
        finally:
            sender.close()

        deadline = time.monotonic() + self.startup_timeout
        reported_error = False
        while time.monotonic() < deadline:
            if receiver.poll(timeout=min(0.1, max(deadline - time.monotonic(), 0.0))):
                try:
                    event = receiver.recv()
                except EOFError:
                    event = None
                if event is not None and event.get("state") == "running":
                    record.runtime_state = RuntimeState.RUNNING
                    return self._response(record, command)
                if event is not None and event.get("state") == "error":
                    record.last_error = str(event.get("detail") or "worker error")
                    reported_error = True
                    break
            if not process.is_alive():
                break

        if reported_error and process.is_alive():
            process.join(timeout=min(1.0, self.terminate_timeout))
        exit_code = process.exitcode
        if process.is_alive():
            self._stop_record(record)
            record.runtime_state = RuntimeState.FAILED
            if reported_error:
                raise WorkerStartError(
                    f"worker {record.loaded.task_id!r} failed to start"
                )
            raise WorkerStartTimeout(
                f"worker {record.loaded.task_id!r} did not become ready in time"
            )

        record.runtime_state = RuntimeState.FAILED
        LOGGER.error(
            "Worker %s failed during startup (exit=%s): %s",
            record.loaded.task_id,
            exit_code,
            record.last_error or "no detail",
        )
        self._close_status_receiver(record)
        try:
            process.close()
        except (OSError, ValueError):
            pass
        record.process = None
        record.stop_event = None
        raise WorkerStartError(f"worker {record.loaded.task_id!r} failed to start")

    def _stop_record(self, record: WorkerRecord | None) -> bool:
        if record is None or record.process is None:
            if record is not None:
                record.runtime_state = RuntimeState.STOPPED
            return False

        process = record.process
        if not process.is_alive():
            process.join(timeout=0)
            record.runtime_state = RuntimeState.STOPPED
            self._dispose_process(record)
            return False

        record.runtime_state = RuntimeState.STOPPING
        if record.stop_event is not None:
            record.stop_event.set()
        process.join(timeout=self.graceful_stop_timeout)
        forced = False
        if process.is_alive():
            forced = True
            process.terminate()
            process.join(timeout=self.terminate_timeout)
        if process.is_alive():
            process.kill()
            process.join(timeout=self.terminate_timeout)
        if process.is_alive():
            record.runtime_state = RuntimeState.FAILED
            record.last_error = "worker remained alive after kill"
            raise WorkerStopError(
                f"worker {record.loaded.task_id!r} could not be stopped"
            )
        record.runtime_state = RuntimeState.STOPPED
        self._dispose_process(record)
        return forced

    def _dispose_process(self, record: WorkerRecord) -> None:
        self._close_status_receiver(record)
        process = record.process
        if process is not None and not process.is_alive():
            try:
                process.close()
            except (OSError, ValueError):
                pass
        record.process = None
        record.stop_event = None

    def _close_status_receiver(self, record: WorkerRecord) -> None:
        if record.status_receiver is not None:
            try:
                record.status_receiver.close()
            except OSError:
                pass
            record.status_receiver = None

    def _get_record(self, task_id: str) -> WorkerRecord | None:
        with self._records_lock:
            return self._records.get(task_id)

    @staticmethod
    def _is_alive(record: WorkerRecord) -> bool:
        return record.process is not None and record.process.is_alive()

    @staticmethod
    def _response(record: WorkerRecord, command: CommandName) -> CommandResponse:
        process = record.process
        pid = process.pid if process is not None and process.is_alive() else None
        return CommandResponse(
            task_id=record.loaded.task_id,
            command=command,
            runtime_state=record.runtime_state,
            pid=pid,
            config_revision=record.loaded.revision,
        )

    def _command_lock(self, task_id: str) -> _NonBlockingLock:
        with self._records_lock:
            lock = self._task_locks.setdefault(task_id, threading.Lock())
        return _NonBlockingLock(lock, task_id)

    def _monitor_processes(self) -> None:
        while not self._closing.wait(0.25):
            with self._records_lock:
                records = list(self._records.values())
            for record in records:
                process = record.process
                if (
                    process is not None
                    and record.runtime_state is RuntimeState.RUNNING
                    and not process.is_alive()
                ):
                    record.runtime_state = RuntimeState.FAILED
                    record.last_error = f"worker exited with code {process.exitcode}"
                    LOGGER.error(
                        "Worker %s exited unexpectedly with code %s",
                        record.loaded.task_id,
                        process.exitcode,
                    )


class _NonBlockingLock:
    def __init__(self, lock: threading.Lock, task_id: str) -> None:
        self._lock = lock
        self._task_id = task_id

    def __enter__(self) -> None:
        if not self._lock.acquire(blocking=False):
            raise WorkerBusyError(
                f"another command is already running for worker {self._task_id!r}"
            )

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self._lock.release()
