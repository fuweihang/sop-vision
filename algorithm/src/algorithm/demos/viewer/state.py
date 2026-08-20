"""Viewer 最新检测结果的生命周期状态。"""

from __future__ import annotations

import time

from algorithm.contracts.detection import FrameDetection


class DetectionOverlayState:
    """保留最新结果，并在一段时间没有新消息后使其过期。"""

    def __init__(self, *, expires_after_seconds: float = 2.0) -> None:
        if expires_after_seconds <= 0:
            raise ValueError("expires_after_seconds must be positive")
        self._expires_after_seconds = expires_after_seconds
        self._message: FrameDetection | None = None
        self._received_at: float | None = None

    @property
    def message(self) -> FrameDetection | None:
        return self._message

    def update(
        self,
        message: FrameDetection,
        *,
        received_at: float | None = None,
    ) -> bool:
        """替换最新结果，返回本次消息是否来自新的 Worker run。"""

        previous_run_id = self._message.run_id if self._message is not None else None
        self._message = message
        self._received_at = time.monotonic() if received_at is None else received_at
        return previous_run_id is not None and previous_run_id != message.run_id

    def expire_if_needed(self, *, now: float | None = None) -> bool:
        """结果超时后清除，只有发生清除时返回 ``True``。"""

        if self._message is None or self._received_at is None:
            return False
        current = time.monotonic() if now is None else now
        if current - self._received_at <= self._expires_after_seconds:
            return False
        self.clear()
        return True

    def clear(self) -> None:
        self._message = None
        self._received_at = None
