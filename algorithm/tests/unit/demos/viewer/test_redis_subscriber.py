import queue
import threading
import time

import redis

from algorithm.contracts.detection import DetectionMetrics, FrameDetection
from algorithm.demos.viewer.redis_subscriber import RedisDetectionSubscriber


def payload(
    *,
    task_id: str = "task-1",
    run_id: str = "run-1",
    frame_id: int = 1,
    published_at_ms: int = 10_000,
) -> str:
    return FrameDetection(
        task_id=task_id,
        camera_id="camera-1",
        source_id="source-1",
        algorithm_id="detector",
        algorithm_version="1",
        run_id=run_id,
        frame_id=frame_id,
        frame_ts_ms=published_at_ms - 1,
        published_at_ms=published_at_ms,
        source_width=100,
        source_height=100,
        objects=(),
        metrics=DetectionMetrics(inference_ms=1.0, fps=10.0),
    ).model_dump_json()


class FakePubSub:
    def __init__(self, trace: list[str]) -> None:
        self.trace = trace
        self.events: queue.Queue[dict] = queue.Queue()
        self.closed = False

    def subscribe(self, *channels: str):
        self.trace.append(f"subscribe:{channels[0]}")
        self.events.put({"type": "subscribe", "data": 1})

    def get_message(self, ignore_subscribe_messages=False, timeout=0.0):
        try:
            return self.events.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self):
        self.closed = True


class FakeRedis:
    def __init__(self, latest: str | None) -> None:
        self.trace: list[str] = []
        self.latest = latest
        self.pubsub_instance = FakePubSub(self.trace)
        self.closed = False

    def pubsub(self, *, ignore_subscribe_messages=False):
        assert ignore_subscribe_messages is False
        return self.pubsub_instance

    def get(self, name: str):
        self.trace.append(f"get:{name}")
        return self.latest

    def close(self):
        self.closed = True


class FailingPubSub(FakePubSub):
    def __init__(self, trace: list[str]) -> None:
        super().__init__(trace)
        self.failed = False

    def get_message(self, ignore_subscribe_messages=False, timeout=0.0):
        event = super().get_message(ignore_subscribe_messages, timeout)
        if event is not None:
            return event
        if not self.failed:
            self.failed = True
            raise redis.ConnectionError("connection lost")
        return None


class FailingRedis(FakeRedis):
    def __init__(self) -> None:
        super().__init__(None)
        self.pubsub_instance = FailingPubSub(self.trace)


def test_subscriber_confirms_subscription_before_reading_latest() -> None:
    fake = FakeRedis(payload())
    received = []
    delivered = threading.Event()
    subscriber = RedisDetectionSubscriber(
        "redis://localhost/0",
        "task-1",
        on_message=lambda message: (received.append(message), delivered.set()),
        client_factory=lambda _url: fake,
        now_ms=lambda: 10_100,
        reconnect_delay_seconds=0.01,
    )

    subscriber.start()
    assert delivered.wait(timeout=1.0)
    subscriber.close()

    assert fake.trace[:2] == [
        "subscribe:vision:telemetry:task-1",
        "get:vision:task:task-1:latest",
    ]
    assert [message.frame_id for message in received] == [1]
    assert fake.pubsub_instance.closed
    assert fake.closed


def test_subscriber_ignores_duplicate_invalid_wrong_task_and_stale_messages() -> None:
    received = []
    subscriber = RedisDetectionSubscriber(
        "redis://localhost/0",
        "task-1",
        on_message=received.append,
        now_ms=lambda: 10_000,
    )

    subscriber._handle_payload("not-json")
    subscriber._handle_payload(payload(task_id="task-2"))
    subscriber._handle_payload(payload(published_at_ms=7_999))
    subscriber._handle_payload(payload(frame_id=2))
    subscriber._handle_payload(payload(frame_id=2))

    assert [message.frame_id for message in received] == [2]


def test_pubsub_message_after_latest_is_delivered_once() -> None:
    fake = FakeRedis(payload(frame_id=1))
    received = []
    two_messages = threading.Event()

    def receive(message: FrameDetection) -> None:
        received.append(message)
        if len(received) == 2:
            two_messages.set()

    subscriber = RedisDetectionSubscriber(
        "redis://localhost/0",
        "task-1",
        on_message=receive,
        client_factory=lambda _url: fake,
        now_ms=lambda: 10_100,
    )
    subscriber.start()
    deadline = time.monotonic() + 1.0
    while not received and time.monotonic() < deadline:
        time.sleep(0.01)
    fake.pubsub_instance.events.put(
        {"type": "message", "data": payload(frame_id=1)}
    )
    fake.pubsub_instance.events.put(
        {"type": "message", "data": payload(frame_id=2)}
    )

    assert two_messages.wait(timeout=1.0)
    subscriber.close()

    assert [message.frame_id for message in received] == [1, 2]


def test_disconnect_clears_overlay_and_reconnects_to_latest() -> None:
    first = FailingRedis()
    second = FakeRedis(payload(frame_id=2))
    clients = iter((first, second))
    reset = threading.Event()
    delivered = threading.Event()
    received = []
    subscriber = RedisDetectionSubscriber(
        "redis://localhost/0",
        "task-1",
        on_message=lambda message: (received.append(message), delivered.set()),
        on_reset=reset.set,
        client_factory=lambda _url: next(clients),
        now_ms=lambda: 10_100,
        reconnect_delay_seconds=0.01,
    )

    subscriber.start()
    assert reset.wait(timeout=1.0)
    assert delivered.wait(timeout=1.0)
    subscriber.close()

    assert [message.frame_id for message in received] == [2]
    assert first.closed
    assert second.closed
