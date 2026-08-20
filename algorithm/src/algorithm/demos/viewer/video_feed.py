"""在后台读取 RTSP，并向 Qt 主线程提供最新 RGB 帧。"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

import cv2
import numpy as np

from algorithm.common.rtsp import Capture, LatestFrameReader, RtspStatus


@dataclass(frozen=True, slots=True)
class RgbFrame:
    sequence: int
    captured_at_ms: int
    pixels: np.ndarray


class LatestRgbFrameBuffer:
    """线程安全且只保留最新图像的交换缓冲。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame: RgbFrame | None = None

    def put(self, frame: RgbFrame) -> None:
        with self._lock:
            self._frame = frame

    def get_latest(self, after_sequence: int = 0) -> RgbFrame | None:
        with self._lock:
            if self._frame is None or self._frame.sequence <= after_sequence:
                return None
            return self._frame

    def clear(self) -> None:
        with self._lock:
            self._frame = None


class RtspVideoFeed:
    """复用 LatestFrameReader，并在另一个线程完成 BGR 到 RGB 的安全复制。"""

    def __init__(
        self,
        url: str,
        *,
        reconnect_delay_seconds: float = 2.0,
        on_status: Callable[[RtspStatus], None] | None = None,
        capture_factory: Callable[[str], Capture] | None = None,
    ) -> None:
        reader_options: dict[str, object] = {
            "reconnect_delay_seconds": reconnect_delay_seconds,
        }
        if capture_factory is not None:
            reader_options["capture_factory"] = capture_factory
        self._reader = LatestFrameReader(url, **reader_options)
        self._on_status = on_status
        self._frames = LatestRgbFrameBuffer()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._reader.start()
        self._thread = threading.Thread(
            target=self._run,
            name="viewer-rtsp-frame-pump",
            daemon=True,
        )
        self._thread.start()

    def get_latest(self, after_sequence: int = 0) -> RgbFrame | None:
        return self._frames.get_latest(after_sequence)

    def close(self, timeout: float = 7.0) -> None:
        self._stop.set()
        self._reader.close()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._frames.clear()

    def _run(self) -> None:
        sequence = 0
        previous_status: RtspStatus | None = None
        while not self._stop.is_set():
            status = self._reader.status()
            if status != previous_status:
                previous_status = status
                if self._on_status is not None:
                    self._on_status(status)

            packet = self._reader.get_latest(sequence, timeout=0.2)
            if packet is None:
                continue
            sequence = packet.sequence
            rgb = cv2.cvtColor(packet.frame, cv2.COLOR_BGR2RGB).copy()
            self._frames.put(
                RgbFrame(
                    sequence=packet.sequence,
                    captured_at_ms=round(packet.captured_at * 1000),
                    pixels=rgb,
                )
            )

        status = self._reader.status()
        if self._on_status is not None and status != previous_status:
            self._on_status(status)
