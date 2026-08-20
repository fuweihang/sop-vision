"""后台订阅实时检测结果并恢复 Redis 最新快照。"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import redis
from pydantic import ValidationError

from algorithm.common.config import redact_url
from algorithm.contracts.detection import FrameDetection

LOGGER = logging.getLogger(__name__)


class RedisPubSub(Protocol):
    def subscribe(self, *channels: str) -> object: ...

    def get_message(
        self,
        ignore_subscribe_messages: bool = False,
        timeout: float = 0.0,
    ) -> dict[str, Any] | None: ...

    def close(self) -> None: ...


class RedisSubscriberClient(Protocol):
    def pubsub(self, *, ignore_subscribe_messages: bool = False) -> RedisPubSub: ...

    def get(self, name: str) -> str | bytes | None: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class RedisSubscriberStatus:
    connected: bool
    detail: str


class RedisDetectionSubscriber:
    """在后台执行 subscribe-then-GET，并向调用方交付有效 v1 消息。"""

    def __init__(
        self,
        redis_url: str,
        task_id: str,
        *,
        on_message: Callable[[FrameDetection], None],
        on_status: Callable[[RedisSubscriberStatus], None] | None = None,
        on_reset: Callable[[], None] | None = None,
        max_message_age_seconds: float = 2.0,
        reconnect_delay_seconds: float = 2.0,
        subscribe_timeout_seconds: float = 3.0,
        client_factory: Callable[[str], RedisSubscriberClient] | None = None,
        now_ms: Callable[[], int] | None = None,
    ) -> None:
        if not task_id:
            raise ValueError("task_id must not be empty")
        if max_message_age_seconds <= 0:
            raise ValueError("max_message_age_seconds must be positive")
        self._redis_url = redis_url
        self._task_id = task_id
        self._channel = f"vision:telemetry:{task_id}"
        self._latest_key = f"vision:task:{task_id}:latest"
        self._on_message = on_message
        self._on_status = on_status
        self._on_reset = on_reset
        self._max_message_age_ms = round(max_message_age_seconds * 1000)
        self._reconnect_delay_seconds = reconnect_delay_seconds
        self._subscribe_timeout_seconds = subscribe_timeout_seconds
        self._client_factory = client_factory or self._default_client_factory
        self._now_ms = now_ms or (lambda: time.time_ns() // 1_000_000)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._connection_lock = threading.Lock()
        self._client: RedisSubscriberClient | None = None
        self._pubsub: RedisPubSub | None = None
        self._seen_order: deque[tuple[str, int]] = deque()
        self._seen: set[tuple[str, int]] = set()
        self._seen_limit = 512
        self._status = RedisSubscriberStatus(False, "not started")

    @property
    def channel(self) -> str:
        return self._channel

    @property
    def latest_key(self) -> str:
        return self._latest_key

    def status(self) -> RedisSubscriberStatus:
        return self._status

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run,
            name="viewer-redis-subscriber",
            daemon=True,
        )
        self._thread.start()

    def close(self, timeout: float = 4.0) -> None:
        self._stop.set()
        self._close_connection()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._set_status(False, "stopped")

    def _run(self) -> None:
        safe_url = redact_url(self._redis_url)
        while not self._stop.is_set():
            self._set_status(False, "connecting")
            try:
                client = self._client_factory(self._redis_url)
                pubsub = client.pubsub(ignore_subscribe_messages=False)
                with self._connection_lock:
                    self._client = client
                    self._pubsub = pubsub

                pubsub.subscribe(self._channel)
                self._wait_until_subscribed(pubsub)
                if self._stop.is_set():
                    break

                self._set_status(True, "subscribed")
                latest = client.get(self._latest_key)
                if latest is not None:
                    self._handle_payload(latest)

                while not self._stop.is_set():
                    event = pubsub.get_message(timeout=0.5)
                    if event is not None and event.get("type") == "message":
                        self._handle_payload(event.get("data"))
            except (redis.RedisError, OSError, TimeoutError, ValueError) as error:
                if not self._stop.is_set():
                    LOGGER.warning("Viewer Redis unavailable (%s): %s", safe_url, error)
                    self._set_status(False, "reconnecting")
                    self._request_reset()
            finally:
                self._close_connection()

            self._stop.wait(self._reconnect_delay_seconds)

        self._close_connection()

    def _wait_until_subscribed(self, pubsub: RedisPubSub) -> None:
        deadline = time.monotonic() + self._subscribe_timeout_seconds
        while not self._stop.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Redis subscribe confirmation timed out")
            event = pubsub.get_message(timeout=min(0.5, remaining))
            if event is None:
                continue
            if event.get("type") == "subscribe":
                return
            if event.get("type") == "message":
                self._handle_payload(event.get("data"))

    def _handle_payload(self, payload: object) -> None:
        if not isinstance(payload, (str, bytes, bytearray)):
            return
        try:
            message = FrameDetection.model_validate_json(payload)
        except (ValidationError, ValueError, TypeError):
            LOGGER.warning("Viewer ignored an invalid frame_detection message")
            return
        if message.task_id != self._task_id:
            return
        age_ms = self._now_ms() - message.published_at_ms
        if age_ms > self._max_message_age_ms:
            return
        identity = (message.run_id, message.frame_id)
        if identity in self._seen:
            return
        if len(self._seen_order) >= self._seen_limit:
            self._seen.discard(self._seen_order.popleft())
        self._seen_order.append(identity)
        self._seen.add(identity)
        self._on_message(message)

    def _request_reset(self) -> None:
        if self._on_reset is not None:
            self._on_reset()

    def _set_status(self, connected: bool, detail: str) -> None:
        self._status = RedisSubscriberStatus(connected, detail)
        if self._on_status is not None:
            self._on_status(self._status)

    def _close_connection(self) -> None:
        with self._connection_lock:
            pubsub = self._pubsub
            client = self._client
            self._pubsub = None
            self._client = None
        if pubsub is not None:
            try:
                pubsub.close()
            except (redis.RedisError, OSError, ValueError):
                pass
        if client is not None:
            try:
                client.close()
            except (redis.RedisError, OSError, ValueError):
                pass

    @staticmethod
    def _default_client_factory(redis_url: str) -> RedisSubscriberClient:
        return redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=3.0,
            socket_timeout=1.0,
            health_check_interval=15,
        )
