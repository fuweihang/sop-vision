import json
import os
import time
import uuid

import pytest
import redis

from algorithm.common.redis_telemetry import RedisTelemetryPublisher
from algorithm.contracts.detection import DetectionMetrics, FrameDetection

REDIS_URL = os.getenv("TEST_REDIS_URL")
pytestmark = pytest.mark.skipif(
    REDIS_URL is None,
    reason="set TEST_REDIS_URL to run Redis integration tests",
)


def test_real_redis_receives_telemetry_and_expiring_latest_snapshot() -> None:
    assert REDIS_URL is not None
    task_id = f"integration-{uuid.uuid4()}"
    channel = f"vision:telemetry:{task_id}"
    latest_key = f"vision:task:{task_id}:latest"
    client = redis.Redis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=3.0,
        socket_timeout=3.0,
    )
    pubsub = client.pubsub(ignore_subscribe_messages=True)
    publisher = RedisTelemetryPublisher(REDIS_URL, channel, latest_key)
    try:
        pubsub.subscribe(channel)
        publisher.start()
        publisher.submit(
            FrameDetection(
                task_id=task_id,
                camera_id="camera-1",
                source_id="source-1",
                algorithm_id="integration-test",
                algorithm_version="1",
                run_id="run-1",
                frame_id=1,
                frame_ts_ms=1,
                published_at_ms=2,
                source_width=100,
                source_height=100,
                objects=(),
                metrics=DetectionMetrics(inference_ms=1.0, fps=1.0),
            )
        )

        deadline = time.monotonic() + 5.0
        received = None
        while received is None and time.monotonic() < deadline:
            received = pubsub.get_message(timeout=0.25)

        assert received is not None
        assert json.loads(received["data"])["task_id"] == task_id
        latest = client.get(latest_key)
        assert latest is not None
        assert json.loads(latest)["frame_id"] == 1
        ttl = client.ttl(latest_key)
        assert 0 < ttl <= 5
    finally:
        publisher.close()
        pubsub.close()
        client.delete(latest_key)
        client.close()
