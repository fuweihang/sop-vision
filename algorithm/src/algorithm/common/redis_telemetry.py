"""不阻塞推理、只保留最新待发送结果的 Redis 发布器。"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import redis

from algorithm.contracts.detection import FrameDetection

from .config import redact_url

LOGGER = logging.getLogger(__name__)


class RedisPipeline(Protocol):
    def set(self, name: str, value: str, *, ex: int) -> RedisPipeline: ...

    def publish(self, channel: str, message: str) -> RedisPipeline: ...

    def execute(self) -> object: ...


class RedisClient(Protocol):
    def pipeline(self, *, transaction: bool = False) -> RedisPipeline: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class RedisTelemetryStatus:
    connected: bool
    detail: str


class RedisTelemetryPublisher:
    """异步发布实时结果；积压时覆盖旧结果而不是阻塞 Worker。"""

    def __init__(
        self,
        redis_url: str,
        channel: str,
        latest_key: str,
        *,
        latest_ttl_seconds: int = 5,
        reconnect_delay_seconds: float = 2.0,
        client_factory: Callable[[str], RedisClient] | None = None,
    ) -> None:
        if latest_ttl_seconds <= 0:
            raise ValueError("latest_ttl_seconds must be positive")
        self._redis_url = redis_url
        self._channel = channel
        self._latest_key = latest_key
        self._latest_ttl_seconds = latest_ttl_seconds
        self._reconnect_delay_seconds = reconnect_delay_seconds
        self._client_factory = client_factory or self._default_client_factory
        self._condition = threading.Condition()
        self._pending: str | None = None
        self._closing = False
        self._thread: threading.Thread | None = None
        self._client: RedisClient | None = None
        self._status = RedisTelemetryStatus(False, "not started")

    def start(self) -> None:
        with self._condition:
            if self._thread is not None:
                return
            self._thread = threading.Thread(
                target=self._run,
                name="redis-telemetry-publisher",
                daemon=True,
            )
            self._thread.start()

    def submit(self, message: FrameDetection) -> None:
        payload = message.model_dump_json(exclude_none=True)
        with self._condition:
            if self._closing:
                return
            self._pending = payload
            self._condition.notify()

    def status(self) -> RedisTelemetryStatus:
        with self._condition:
            return self._status

    def close(self, timeout: float = 3.0) -> None:
        with self._condition:
            self._closing = True
            self._condition.notify_all()
            thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        self._close_client()
        self._set_status(False, "stopped")

    def _run(self) -> None:
        safe_url = redact_url(self._redis_url)
        while True:
            with self._condition:
                while self._pending is None and not self._closing:
                    self._condition.wait()
                if self._pending is None and self._closing:
                    break
                payload = self._pending
                self._pending = None

            try:
                if self._client is None:
                    self._set_status(False, "connecting")
                    self._client = self._client_factory(self._redis_url)
                pipeline = self._client.pipeline(transaction=False)
                pipeline.set(
                    self._latest_key,
                    payload,
                    ex=self._latest_ttl_seconds,
                )
                pipeline.publish(self._channel, payload)
                pipeline.execute()
                self._set_status(True, "publishing")
            except (redis.RedisError, OSError, ValueError) as error:
                LOGGER.warning("Redis telemetry unavailable (%s): %s", safe_url, error)
                self._close_client()
                self._set_status(False, "reconnecting")
                with self._condition:
                    if self._closing:
                        break
                    if self._pending is None:
                        self._pending = payload
                    self._condition.wait(timeout=self._reconnect_delay_seconds)

        self._close_client()

    def _close_client(self) -> None:
        client = self._client
        self._client = None
        if client is not None:
            try:
                client.close()
            except (redis.RedisError, OSError, ValueError):
                pass

    def _set_status(self, connected: bool, detail: str) -> None:
        with self._condition:
            self._status = RedisTelemetryStatus(connected, detail)

    @staticmethod
    def _default_client_factory(redis_url: str) -> RedisClient:
        return redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=3.0,
            socket_timeout=3.0,
            health_check_interval=15,
        )
