"""只保留最新帧的 RTSP 读取器，内存有界并支持自动重连。"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import cv2
import numpy as np

from .config import redact_url

LOGGER = logging.getLogger(__name__)


class Capture(Protocol):
    def isOpened(self) -> bool: ...  # noqa: N802

    def read(self) -> tuple[bool, np.ndarray | None]: ...

    def release(self) -> None: ...


@dataclass(frozen=True, slots=True)
class FramePacket:
    sequence: int
    captured_at: float
    frame: np.ndarray


@dataclass(frozen=True, slots=True)
class RtspStatus:
    connected: bool
    detail: str


def open_rtsp_capture(url: str) -> Capture:
    """打开 RTSP，在后端支持时为网络操作设置有限超时（timeout）。"""

    parameters: list[int] = []
    if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
        parameters.extend([cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5_000])
    if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
        parameters.extend([cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5_000])

    try:
        capture = cv2.VideoCapture(url, cv2.CAP_FFMPEG, parameters)
    except (cv2.error, TypeError):
        capture = cv2.VideoCapture(url)
    if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return capture


class LatestFrameReader:
    """持续解码 RTSP，但只保留最新一帧（newest frame）。"""

    def __init__(
        self,
        url: str,
        *,
        reconnect_delay_seconds: float = 2.0,
        capture_factory: Callable[[str], Capture] = open_rtsp_capture,
    ) -> None:
        self._url = url
        self._reconnect_delay_seconds = reconnect_delay_seconds
        self._capture_factory = capture_factory
        self._stop = threading.Event()
        self._condition = threading.Condition()
        self._packet: FramePacket | None = None
        self._capture: Capture | None = None
        self._status = RtspStatus(False, "not started")
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """启动后台解码线程；已启动时直接返回。"""

        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run,
            name="rtsp-latest-frame",
            daemon=True,
        )
        self._thread.start()

    def get_latest(
        self, after_sequence: int = 0, timeout: float = 0.5
    ) -> FramePacket | None:
        """获取序号大于 ``after_sequence`` 的最新帧；超时返回 ``None``。"""

        deadline = time.monotonic() + timeout
        with self._condition:
            while not self._stop.is_set():
                if self._packet is not None and self._packet.sequence > after_sequence:
                    return self._packet
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(remaining)
        return None

    def status(self) -> RtspStatus:
        """返回当前 RTSP 连接状态。"""

        with self._condition:
            return self._status

    def close(self) -> None:
        """停止解码线程并释放视频捕获资源。"""

        self._stop.set()
        with self._condition:
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=6.0)
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def _run(self) -> None:
        """后台线程主循环：持续读帧，断开时按间隔重连。"""

        sequence = 0
        safe_url = redact_url(self._url)
        while not self._stop.is_set():
            self._set_status(False, "connecting")
            LOGGER.info("Opening RTSP stream %s", safe_url)
            try:
                capture = self._capture_factory(self._url)
                self._capture = capture
                if not capture.isOpened():
                    raise ConnectionError("VideoCapture could not open the stream")
                self._set_status(True, "connected")

                while not self._stop.is_set():
                    ok, frame = capture.read()
                    if not ok or frame is None:
                        raise ConnectionError("RTSP frame read failed")
                    sequence += 1
                    packet = FramePacket(sequence, time.time(), frame)
                    with self._condition:
                        self._packet = packet
                        self._condition.notify_all()
            except Exception as error:
                if not self._stop.is_set():
                    LOGGER.warning("RTSP unavailable (%s): %s", safe_url, error)
                    self._set_status(False, "reconnecting")
            finally:
                if self._capture is not None:
                    self._capture.release()
                    self._capture = None

            self._stop.wait(self._reconnect_delay_seconds)

        self._set_status(False, "stopped")

    def _set_status(self, connected: bool, detail: str) -> None:
        """在条件变量保护下更新连接状态并唤醒等待者。"""

        with self._condition:
            self._status = RtspStatus(connected, detail)
            self._condition.notify_all()
