import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from algorithm.daemon.configuration import WorkerConfigurationError
from algorithm.daemon.manager import (
    WorkerAlreadyRunningError,
    WorkerBusyError,
    WorkerManager,
    WorkerPoolFullError,
    WorkerStartError,
)
from algorithm.database import TaskParameterRecord


def task_record(task_id: str = "detector-001", *, confidence: float = 0.5):
    return TaskParameterRecord(
        task_id=task_id,
        worker_type="detector",
        config={
            "camera_id": "camera-001",
            "source_id": "source-001",
            "rtsp_url": "rtsp://camera/stream",
            "redis_url": "redis://localhost/0",
            "model_path": "model.pt",
            "confidence": confidence,
        },
        updated_at=datetime(2026, 8, 21, tzinfo=UTC),
    )


class FakeRepository:
    def __init__(self, *records: TaskParameterRecord) -> None:
        self.records = {record.task_id: record for record in records}
        self.closed = False

    def get(self, task_id):
        return self.records.get(task_id)

    def ping(self):
        return True

    def close(self):
        self.closed = True


class FakeReceiver:
    def __init__(self, messages) -> None:
        self.messages = messages

    def poll(self, timeout=0):
        return bool(self.messages)

    def recv(self):
        return self.messages.pop(0)

    def close(self):
        pass


class FakeSender:
    def __init__(self, messages) -> None:
        self.messages = messages

    def send(self, message):
        self.messages.append(message)

    def close(self):
        pass


class FakeProcess:
    next_pid = 1000

    def __init__(self, *, args, **_kwargs) -> None:
        self.args = args
        self.pid = None
        self.exitcode = None
        self.alive = False
        self.ignore_graceful_stop = False

    def start(self):
        type(self).next_pid += 1
        self.pid = type(self).next_pid
        self.alive = True
        self.args[-1].send({"state": "running"})

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        if self.args[-2].is_set() and not self.ignore_graceful_stop:
            self.alive = False
            self.exitcode = 0

    def terminate(self):
        self.alive = False
        self.exitcode = -15

    def kill(self):
        self.alive = False
        self.exitcode = -9

    def close(self):
        pass


class FakeContext:
    def __init__(self) -> None:
        self.processes = []

    def Pipe(self, duplex=False):
        assert duplex is False
        messages = []
        return FakeReceiver(messages), FakeSender(messages)

    def Event(self):
        return threading.Event()

    def Process(self, **kwargs):
        process = FakeProcess(**kwargs)
        self.processes.append(process)
        return process


class FailingProcess(FakeProcess):
    def start(self):
        raise RuntimeError("spawn failed")


class FailingContext(FakeContext):
    def Process(self, **kwargs):
        process = FailingProcess(**kwargs)
        self.processes.append(process)
        return process


def manager_for(repository, tmp_path: Path, **kwargs):
    return WorkerManager(
        repository,
        tmp_path,
        process_context=kwargs.pop("process_context", FakeContext()),
        **kwargs,
    )


def test_manager_does_not_autostart_and_reload_uses_latest_database_config(
    tmp_path: Path,
) -> None:
    repository = FakeRepository(task_record(confidence=0.5))
    context = FakeContext()
    manager = manager_for(repository, tmp_path, process_context=context)
    try:
        assert context.processes == []
        started = manager.start("detector-001")
        assert started.runtime_state == "running"
        assert context.processes[-1].args[2]["confidence"] == 0.5
        with pytest.raises(WorkerAlreadyRunningError):
            manager.start("detector-001")

        repository.records["detector-001"] = task_record(confidence=0.7)
        manager.reload("detector-001")
        assert context.processes[-1].args[2]["confidence"] == 0.7
    finally:
        manager.close()


def test_invalid_reload_keeps_live_worker_running(tmp_path: Path) -> None:
    repository = FakeRepository(task_record())
    context = FakeContext()
    manager = manager_for(repository, tmp_path, process_context=context)
    try:
        manager.start("detector-001")
        repository.records["detector-001"] = task_record(confidence=2)
        with pytest.raises(WorkerConfigurationError):
            manager.reload("detector-001")
        assert context.processes[-1].is_alive()
    finally:
        manager.close()


def test_process_capacity_rejects_new_task_and_stop_releases_slot(
    tmp_path: Path,
) -> None:
    repository = FakeRepository(task_record("task-1"), task_record("task-2"))
    manager = manager_for(repository, tmp_path, max_workers=1)
    try:
        manager.start("task-1")
        assert manager.active_workers == 1
        with pytest.raises(WorkerPoolFullError):
            manager.start("task-2")
        manager.stop("task-1")
        manager.start("task-2")
        assert manager.active_workers == 1
    finally:
        manager.close()


def test_spawn_failure_releases_reserved_pool_slot(tmp_path: Path) -> None:
    manager = manager_for(
        FakeRepository(task_record()), tmp_path, process_context=FailingContext()
    )
    try:
        with pytest.raises(WorkerStartError):
            manager.start("detector-001")
        assert manager.active_workers == 0
    finally:
        manager.close()


def test_stop_terminates_worker_that_ignores_graceful_event(tmp_path: Path) -> None:
    repository = FakeRepository(task_record())
    context = FakeContext()
    manager = manager_for(
        repository,
        tmp_path,
        graceful_stop_timeout=0.0,
        terminate_timeout=0.0,
        process_context=context,
    )
    try:
        manager.start("detector-001")
        context.processes[-1].ignore_graceful_stop = True
        stopped = manager.stop("detector-001")
        assert stopped.forced_stop is True
        assert stopped.runtime_state == "stopped"
        assert context.processes[-1].exitcode == -15
        assert manager.active_workers == 0
    finally:
        manager.close()


def test_stop_is_idempotent_for_configured_inactive_task(tmp_path: Path) -> None:
    manager = manager_for(FakeRepository(task_record()), tmp_path)
    try:
        stopped = manager.stop("detector-001")
        assert stopped.runtime_state == "stopped"
        assert stopped.pid is None
    finally:
        manager.close()


def test_concurrent_command_for_same_task_is_rejected(tmp_path: Path) -> None:
    manager = manager_for(FakeRepository(task_record()), tmp_path)
    try:
        with (
            manager._command_lock("detector-001"),
            pytest.raises(WorkerBusyError),
        ):
            manager.start("detector-001")
    finally:
        manager.close()


def test_unexpected_exit_releases_pool_slot_without_restart(tmp_path: Path) -> None:
    context = FakeContext()
    manager = manager_for(
        FakeRepository(task_record()), tmp_path, process_context=context
    )
    try:
        manager.start("detector-001")
        context.processes[-1].alive = False
        context.processes[-1].exitcode = 1
        time.sleep(0.35)
        assert len(context.processes) == 1
        assert manager.active_workers == 0
    finally:
        manager.close()
