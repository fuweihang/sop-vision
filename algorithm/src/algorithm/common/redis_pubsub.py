"""Redis Pub/Sub listener for runtime ROI updates."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import redis
from pydantic import ValidationError

from .config import redact_url
from .roi import RoiState

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RedisStatus:
    connected: bool
    detail: str


class RedisRoiSubscriber:
    """Maintain a background subscription without blocking video inference."""

    def __init__(
        self,
        redis_url: str,
        channel: str,
        task_id: str,
        roi_state: RoiState,
        *,
        reconnect_delay_seconds: float = 2.0,
    ) -> None:
        self._redis_url = redis_url
        self._channel = channel
        self._task_id = task_id
        self._roi_state = roi_state
        self._reconnect_delay_seconds = reconnect_delay_seconds
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._status = RedisStatus(False, "not started")
        self._thread: threading.Thread | None = None
        self._client: redis.Redis | None = None
        self._pubsub: redis.client.PubSub | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run,
            name="redis-roi-subscriber",
            daemon=True,
        )
        self._thread.start()

    def status(self) -> RedisStatus:
        with self._lock:
            return self._status

    def close(self) -> None:
        self._stop.set()
        # Closing the active subscription unblocks get_message immediately.
        if self._pubsub is not None:
            try:
                self._pubsub.close()
            except (redis.RedisError, OSError, ValueError):
                pass
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        self._close_connections()

    def apply_message(self, payload: str | bytes) -> bool:
        """Validate one message and atomically apply it; invalid input is ignored."""

        try:
            update = self._roi_state.apply_payload(payload, self._task_id)
        except (ValidationError, ValueError) as error:
            LOGGER.warning("Ignoring invalid ROI update: %s", error)
            return False

        if update.enabled:
            LOGGER.info(
                "Applied ROI %s with %d points for task %s",
                update.roi_id,
                len(update.points),
                update.task_id,
            )
        else:
            LOGGER.info("Cleared ROI for task %s", update.task_id)
        return True

    def _run(self) -> None:
        safe_url = redact_url(self._redis_url)
        while not self._stop.is_set():
            self._set_status(False, "connecting")
            try:
                self._client = redis.Redis.from_url(
                    self._redis_url,
                    decode_responses=True,
                    socket_connect_timeout=3.0,
                    socket_timeout=3.0,
                    health_check_interval=15,
                )
                self._pubsub = self._client.pubsub(ignore_subscribe_messages=True)
                self._pubsub.subscribe(self._channel)
                self._set_status(True, "subscribed")
                LOGGER.info("Subscribed to Redis ROI channel %s", self._channel)

                while not self._stop.is_set():
                    message = self._pubsub.get_message(timeout=1.0)
                    if message is not None and message.get("type") == "message":
                        self.apply_message(message["data"])
            except (redis.RedisError, OSError, ValueError) as error:
                if not self._stop.is_set():
                    LOGGER.warning("Redis unavailable (%s): %s", safe_url, error)
                    self._set_status(False, "reconnecting")
            finally:
                self._close_connections()

            self._stop.wait(self._reconnect_delay_seconds)

        self._set_status(False, "stopped")

    def _close_connections(self) -> None:
        if self._pubsub is not None:
            try:
                self._pubsub.close()
            except (redis.RedisError, OSError, ValueError):
                pass
            self._pubsub = None
        if self._client is not None:
            try:
                self._client.close()
            except (redis.RedisError, OSError, ValueError):
                pass
            self._client = None

    def _set_status(self, connected: bool, detail: str) -> None:
        with self._lock:
            self._status = RedisStatus(connected, detail)
