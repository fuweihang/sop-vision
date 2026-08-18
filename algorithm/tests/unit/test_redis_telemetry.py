import json
import threading
import time

from algorithm.common.redis_telemetry import RedisTelemetryPublisher
from algorithm.contracts.detection import DetectionMetrics, FrameDetection


def message(frame_id: int) -> FrameDetection:
    return FrameDetection(
        task_id="task-1",
        camera_id="camera-1",
        source_id="source-1",
        algorithm_id="detector",
        algorithm_version="1",
        run_id="run-1",
        frame_id=frame_id,
        frame_ts_ms=1000,
        published_at_ms=1001,
        source_width=100,
        source_height=100,
        objects=(),
        metrics=DetectionMetrics(inference_ms=1.0, fps=10.0),
    )


class FakePipeline:
    def __init__(self, client) -> None:
        self.client = client
        self.commands = []

    def set(self, name, value, *, ex):
        self.commands.append(("set", name, value, ex))
        return self

    def publish(self, channel, message):
        self.commands.append(("publish", channel, message))
        return self

    def execute(self):
        if not self.client.executions:
            self.client.first_started.set()
            self.client.release_first.wait(timeout=2.0)
        self.client.executions.append(self.commands)
        return [True, 1]


class FakeRedis:
    def __init__(self) -> None:
        self.executions = []
        self.first_started = threading.Event()
        self.release_first = threading.Event()
        self.closed = False

    def pipeline(self, *, transaction=False):
        assert transaction is False
        return FakePipeline(self)

    def close(self):
        self.closed = True


def wait_for_count(fake: FakeRedis, count: int) -> None:
    deadline = time.monotonic() + 2.0
    while len(fake.executions) < count and time.monotonic() < deadline:
        time.sleep(0.01)
    assert len(fake.executions) >= count


def test_publisher_sets_latest_and_publishes_same_payload() -> None:
    fake = FakeRedis()
    fake.release_first.set()
    publisher = RedisTelemetryPublisher(
        "redis://localhost/0",
        "vision:telemetry:task-1",
        "vision:task:task-1:latest",
        client_factory=lambda _url: fake,
    )
    publisher.start()
    publisher.submit(message(1))
    wait_for_count(fake, 1)
    publisher.close()

    set_command, publish_command = fake.executions[0]
    assert set_command[0:2] == ("set", "vision:task:task-1:latest")
    assert set_command[3] == 5
    assert publish_command[0:2] == ("publish", "vision:telemetry:task-1")
    assert json.loads(set_command[2]) == json.loads(publish_command[2])
    assert fake.closed


def test_slow_publisher_keeps_only_newest_pending_frame() -> None:
    fake = FakeRedis()
    publisher = RedisTelemetryPublisher(
        "redis://localhost/0",
        "channel",
        "latest",
        client_factory=lambda _url: fake,
    )
    publisher.start()
    publisher.submit(message(1))
    assert fake.first_started.wait(timeout=2.0)
    publisher.submit(message(2))
    publisher.submit(message(3))
    fake.release_first.set()
    wait_for_count(fake, 2)
    publisher.close()

    frame_ids = [json.loads(commands[0][2])["frame_id"] for commands in fake.executions]
    assert frame_ids == [1, 3]
