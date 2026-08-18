import json
import threading
import time
from pathlib import Path

import pytest

from algorithm.daemon.config_loader import ConfigLoadError
from algorithm.daemon.manager import (
    WorkerBusyError,
    WorkerManager,
    WorkerNotFoundError,
)


def document(*, confidence: float = 0.5) -> dict:
    return {
        "schema_version": 1,
        "workers": {
            "detector-001": {
                "type": "detector",
                "config": {
                    "camera_id": "camera-001",
                    "source_id": "source-001",
                    "rtsp_url": "rtsp://camera/stream",
                    "redis_url": "redis://localhost/0",
                    "model_path": "model.pt",
                    "confidence": confidence,
                },
            }
        },
    }


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


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
        self.closed = False
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
        self.closed = True


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


def test_manager_does_not_autostart_and_distinguishes_restart_from_reload(
    tmp_path,
) -> None:
    path = tmp_path / "config.json"
    write(path, document(confidence=0.5))
    context = FakeContext()
    manager = WorkerManager(path, process_context=context)
    try:
        assert context.processes == []

        started = manager.start("detector-001")
        assert started.runtime_state == "running"
        assert context.processes[-1].args[2]["confidence"] == 0.5

        write(path, document(confidence=0.7))
        manager.restart("detector-001")
        assert context.processes[-1].args[2]["confidence"] == 0.5

        manager.reload("detector-001")
        assert context.processes[-1].args[2]["confidence"] == 0.7
    finally:
        manager.close()


def test_invalid_reload_stops_worker_but_keeps_last_valid_config(tmp_path) -> None:
    path = tmp_path / "config.json"
    write(path, document())
    context = FakeContext()
    manager = WorkerManager(path, process_context=context)
    try:
        manager.start("detector-001")
        path.write_text("{broken", encoding="utf-8")

        with pytest.raises(ConfigLoadError):
            manager.reload("detector-001")
        assert not context.processes[-1].is_alive()

        restored = manager.restart("detector-001")
        assert restored.runtime_state == "running"
    finally:
        manager.close()


def test_valid_config_removing_task_clears_cached_restart_config(tmp_path) -> None:
    path = tmp_path / "config.json"
    write(path, document())
    manager = WorkerManager(path, process_context=FakeContext())
    try:
        manager.start("detector-001")
        write(path, {"schema_version": 1, "workers": {}})

        with pytest.raises(WorkerNotFoundError):
            manager.reload("detector-001")
        with pytest.raises(WorkerNotFoundError):
            manager.restart("detector-001")
    finally:
        manager.close()


def test_stop_terminates_worker_that_ignores_graceful_event(tmp_path) -> None:
    path = tmp_path / "config.json"
    write(path, document())
    context = FakeContext()
    manager = WorkerManager(
        path,
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
    finally:
        manager.close()


def test_concurrent_command_for_same_task_is_rejected(tmp_path) -> None:
    path = tmp_path / "config.json"
    write(path, document())
    manager = WorkerManager(path, process_context=FakeContext())
    try:
        with manager._command_lock("detector-001"):
            with pytest.raises(WorkerBusyError):
                manager.start("detector-001")
    finally:
        manager.close()


def test_unexpected_exit_does_not_automatically_restart_worker(tmp_path) -> None:
    path = tmp_path / "config.json"
    write(path, document())
    context = FakeContext()
    manager = WorkerManager(path, process_context=context)
    try:
        manager.start("detector-001")
        context.processes[-1].alive = False
        context.processes[-1].exitcode = 1
        time.sleep(0.35)

        assert len(context.processes) == 1
    finally:
        manager.close()
