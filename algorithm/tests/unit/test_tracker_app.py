import threading
from pathlib import Path

import numpy as np

from algorithm.algorithms.yolo import Detection, DetectionBatch
from algorithm.common.rtsp import FramePacket
from algorithm.workers.tracker import app as tracker_module
from algorithm.workers.tracker.config import TrackerConfig


def tracker_config() -> TrackerConfig:
    return TrackerConfig(
        task_id="tracker-001",
        rtsp_url="rtsp://camera/stream",
        redis_url="redis://localhost/0",
        model_path=Path("model.pt"),
    )


def test_tracker处理连续帧并释放资源(monkeypatch) -> None:
    stop = threading.Event()

    class FakeTracker:
        instance = None

        def __init__(self, *_args, **_kwargs) -> None:
            self.track_count = 0
            FakeTracker.instance = self

        def track(self, _frame: np.ndarray) -> DetectionBatch:
            self.track_count += 1
            return DetectionBatch(
                detections=(
                    Detection(
                        0,
                        "person",
                        0.9,
                        (1.0, 1.0, 8.0, 8.0),
                        track_id=self.track_count,
                    ),
                ),
                inference_ms=4.0,
            )

    class FakeReader:
        instance = None

        def __init__(self, *_args, **_kwargs) -> None:
            self.started = False
            self.closed = False
            self._packets = [
                FramePacket(1, 1.0, np.zeros((10, 10, 3), dtype=np.uint8)),
                FramePacket(2, 2.0, np.zeros((10, 10, 3), dtype=np.uint8)),
            ]
            FakeReader.instance = self

        def start(self) -> None:
            self.started = True

        def get_latest(self, _after_sequence: int, timeout: float = 0.1):
            assert timeout == 0.1
            if self._packets:
                return self._packets.pop(0)
            stop.set()
            return None

        def close(self) -> None:
            self.closed = True

    class FakePublisher:
        instance = None

        def __init__(self, *_args, **_kwargs) -> None:
            self.started = False
            self.closed = False
            self.messages = []
            FakePublisher.instance = self

        def start(self) -> None:
            self.started = True

        def submit(self, message) -> None:
            self.messages.append(message)

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(tracker_module, "YoloTracker", FakeTracker)
    monkeypatch.setattr(tracker_module, "LatestFrameReader", FakeReader)
    monkeypatch.setattr(tracker_module, "RedisTelemetryPublisher", FakePublisher)
    monkeypatch.setattr(
        tracker_module,
        "install_stop_signal_handlers",
        lambda _stop: {},
    )
    monkeypatch.setattr(
        tracker_module,
        "restore_signal_handlers",
        lambda _previous: None,
    )
    ready = []

    tracker_module.run_tracker(
        tracker_config(),
        stop_event=stop,
        ready_callback=lambda: ready.append(True),
    )

    assert ready == [True]
    assert FakeTracker.instance is not None
    assert FakeTracker.instance.track_count == 2
    assert FakeReader.instance is not None
    assert FakeReader.instance.started
    assert FakeReader.instance.closed
    assert FakePublisher.instance is not None
    assert FakePublisher.instance.started
    assert FakePublisher.instance.closed
    assert [
        message.objects[0].track_id for message in FakePublisher.instance.messages
    ] == [1, 2]
    assert len(
        {message.run_id for message in FakePublisher.instance.messages}
    ) == 1


def test_tracker重启后创建新实例和run_id(monkeypatch) -> None:
    active_stop: threading.Event | None = None
    tracker_instances = []
    messages = []

    class FakeTracker:
        def __init__(self, *_args, **_kwargs) -> None:
            tracker_instances.append(self)

        def track(self, _frame: np.ndarray) -> DetectionBatch:
            return DetectionBatch(
                detections=(
                    Detection(0, "person", 0.9, (1.0, 1.0, 8.0, 8.0), 1),
                ),
                inference_ms=4.0,
            )

    class OneFrameReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self._returned = False

        def start(self) -> None:
            pass

        def get_latest(self, _after_sequence: int, timeout: float = 0.1):
            assert timeout == 0.1
            if not self._returned:
                self._returned = True
                return FramePacket(
                    1,
                    1.0,
                    np.zeros((10, 10, 3), dtype=np.uint8),
                )
            assert active_stop is not None
            active_stop.set()
            return None

        def close(self) -> None:
            pass

    class CollectingPublisher:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def start(self) -> None:
            pass

        def submit(self, message) -> None:
            messages.append(message)

        def close(self) -> None:
            pass

    monkeypatch.setattr(tracker_module, "YoloTracker", FakeTracker)
    monkeypatch.setattr(tracker_module, "LatestFrameReader", OneFrameReader)
    monkeypatch.setattr(
        tracker_module,
        "RedisTelemetryPublisher",
        CollectingPublisher,
    )
    monkeypatch.setattr(
        tracker_module,
        "install_stop_signal_handlers",
        lambda _stop: {},
    )
    monkeypatch.setattr(
        tracker_module,
        "restore_signal_handlers",
        lambda _previous: None,
    )

    for _ in range(2):
        active_stop = threading.Event()
        tracker_module.run_tracker(tracker_config(), stop_event=active_stop)

    assert len(tracker_instances) == 2
    assert len(messages) == 2
    assert messages[0].run_id != messages[1].run_id
