"""Bounded lifecycle manager for long-running AIWorker processes."""

from __future__ import annotations

import logging
import multiprocessing
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from algorithm.database import TaskParameterRecord
from algorithm.workers.base import worker_process_main

from .configuration import LoadedWorker, validate_record
from .models import CommandName, CommandResponse, RuntimeState

LOGGER = logging.getLogger(__name__)


class TaskRepository(Protocol):
    def get(self, task_id: str) -> TaskParameterRecord | None: ...

    def ping(self) -> bool: ...

    def close(self) -> None: ...


class WorkerManagerError(RuntimeError):
    pass


class WorkerNotFoundError(WorkerManagerError):
    pass


class WorkerBusyError(WorkerManagerError):
    pass


class WorkerAlreadyRunningError(WorkerManagerError):
    pass


class WorkerPoolFullError(WorkerManagerError):
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
    status_receiver: Any | None = None
    runtime_state: RuntimeState = RuntimeState.STOPPED
    last_error: str | None = None
    slot_reserved: bool = False


class WorkerManager:
    """Serialize commands per task and enforce a global process capacity."""

    def __init__(
        self,
        repository: TaskRepository,
        resource_root: Path,
        *,
        max_workers: int = 4,
        startup_timeout: float = 60.0,
        graceful_stop_timeout: float = 10.0,
        terminate_timeout: float = 3.0,
        process_context: Any | None = None,
    ) -> None:
        if max_workers <= 0:
            raise ValueError("max_workers must be positive")
        self.repository = repository
        self.resource_root = resource_root.expanduser().resolve()
        self.max_workers = max_workers
        self.startup_timeout = startup_timeout
        self.graceful_stop_timeout = graceful_stop_timeout
        self.terminate_timeout = terminate_timeout
        self._context = process_context or multiprocessing.get_context("spawn")
        self._records: dict[str, WorkerRecord] = {}
        self._records_lock = threading.Lock()
        self._task_locks: dict[str, threading.Lock] = {}
        self._closing = threading.Event()
        self._monitor = threading.Thread(
            target=self._monitor_processes,
            name="worker-process-monitor",
            daemon=True,
        )
        self._monitor.start()

    @property
    def active_workers(self) -> int:
        with self._records_lock:
            return sum(record.slot_reserved for record in self._records.values())

    def database_is_reachable(self) -> bool:
        return self.repository.ping()

    def start(self, task_id: str) -> CommandResponse:
        with self._command_lock(task_id):
            record = self._get_record(task_id)
            if record is not None and self._is_alive(record):
                raise WorkerAlreadyRunningError(
                    f"worker {task_id!r} is already running"
                )
            if record is not None:
                self._dispose_if_dead(record)
            loaded = self._load_task(task_id)
            record = self._replace_loaded(record, loaded)
            return self._spawn_and_wait(record, CommandName.START)

    def reload(self, task_id: str) -> CommandResponse:
        with self._command_lock(task_id):
            # Validate the committed snapshot before disrupting a live Worker.
            loaded = self._load_task(task_id)
            record = self._get_record(task_id)
            preserve_slot = record is not None and record.slot_reserved
            forced = (
                self._stop_record(record, preserve_slot=preserve_slot)
                if record is not None
                else False
            )
            record = self._replace_loaded(record, loaded)
            response = self._spawn_and_wait(record, CommandName.RELOAD)
            return response.model_copy(update={"forced_stop": forced})

    def stop(self, task_id: str) -> CommandResponse:
        with self._command_lock(task_id):
            record = self._get_record(task_id)
            if record is None:
                record = self._replace_loaded(None, self._load_task(task_id))
            forced = self._stop_record(record)
            response = self._response(record, CommandName.STOP)
            return response.model_copy(update={"forced_stop": forced})

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
        self.repository.close()

    def _load_task(self, task_id: str) -> LoadedWorker:
        record = self.repository.get(task_id)
        if record is None:
            raise WorkerNotFoundError(f"worker {task_id!r} is not configured")
        return validate_record(record, self.resource_root)

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

    def _reserve_slot(self, record: WorkerRecord) -> None:
        with self._records_lock:
            if record.slot_reserved:
                return
            active = sum(item.slot_reserved for item in self._records.values())
            if active >= self.max_workers:
                raise WorkerPoolFullError(
                    f"worker process capacity {self.max_workers} is exhausted"
                )
            record.slot_reserved = True

    def _release_slot(self, record: WorkerRecord) -> None:
        with self._records_lock:
            record.slot_reserved = False

    def _spawn_and_wait(
        self,
        record: WorkerRecord,
        command: CommandName,
    ) -> CommandResponse:
        self._reserve_slot(record)
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
            self._release_slot(record)
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
        self._dispose_process(record)
        raise WorkerStartError(f"worker {record.loaded.task_id!r} failed to start")

    def _stop_record(
        self,
        record: WorkerRecord | None,
        *,
        preserve_slot: bool = False,
    ) -> bool:
        if record is None or record.process is None:
            if record is not None:
                record.runtime_state = RuntimeState.STOPPED
                if not preserve_slot:
                    self._release_slot(record)
            return False

        process = record.process
        if not process.is_alive():
            process.join(timeout=0)
            record.runtime_state = RuntimeState.STOPPED
            self._dispose_process(record, preserve_slot=preserve_slot)
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
        self._dispose_process(record, preserve_slot=preserve_slot)
        return forced

    def _dispose_if_dead(self, record: WorkerRecord) -> None:
        process = record.process
        if process is not None and not process.is_alive():
            process.join(timeout=0)
            self._dispose_process(record)

    def _dispose_process(
        self,
        record: WorkerRecord,
        *,
        preserve_slot: bool = False,
    ) -> None:
        self._close_status_receiver(record)
        process = record.process
        if process is not None and not process.is_alive():
            try:
                process.close()
            except (OSError, ValueError):
                pass
        record.process = None
        record.stop_event = None
        if not preserve_slot:
            self._release_slot(record)

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
            config_updated_at=record.loaded.updated_at,
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
                    exit_code = process.exitcode
                    record.runtime_state = RuntimeState.FAILED
                    record.last_error = f"worker exited with code {exit_code}"
                    LOGGER.error(
                        "Worker %s exited unexpectedly with code %s",
                        record.loaded.task_id,
                        exit_code,
                    )
                    self._dispose_process(record)


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
