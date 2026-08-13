"""Detector 进程生命周期与组件编排（process lifecycle & orchestration）。"""

from __future__ import annotations

import logging
import signal
import threading
import time

import cv2
import numpy as np

from algorithm.algorithms.object_detection.yolo import Detection, YoloDetector
from algorithm.common.config import DetectorConfig, redact_url
from algorithm.common.redis_pubsub import RedisRoiSubscriber
from algorithm.common.roi import RoiState, RoiUpdate, bbox_center_is_inside_roi
from algorithm.common.rtsp import LatestFrameReader

from .renderer import render_detector_frame

LOGGER = logging.getLogger(__name__)


def run_detector(config: DetectorConfig) -> None:
    """运行主循环，直到窗口关闭、按下退出键或收到信号（signal）为止。"""

    stop = threading.Event()
    previous_signal_handlers = _install_signal_handlers(stop)
    roi_state = RoiState()
    subscriber = RedisRoiSubscriber(
        config.redis_url,
        config.roi_channel,
        config.task_id,
        roi_state,
        reconnect_delay_seconds=config.reconnect_delay_seconds,
    )
    reader = LatestFrameReader(
        config.rtsp_url,
        reconnect_delay_seconds=config.reconnect_delay_seconds,
    )

    LOGGER.info("Starting detector task %s", config.task_id)
    LOGGER.info("RTSP source: %s", redact_url(config.rtsp_url))
    LOGGER.info("ROI channel: %s", config.roi_channel)
    LOGGER.info("Loading YOLO model from %s", config.model_path)
    LOGGER.info("YOLO inference device: %s", config.device or "auto")

    subscriber.start()
    try:
        detector = YoloDetector(
            config.model_path,
            image_size=config.image_size,
            confidence=config.confidence,
            device=config.device,
        )
        reader.start()
        cv2.namedWindow(config.window_name, cv2.WINDOW_NORMAL)

        last_sequence = 0
        raw_frame = np.zeros((360, 640, 3), dtype=np.uint8)
        detections: tuple[Detection, ...] = ()
        inference_ms = 0.0
        fps = 0.0
        previous_frame_at: float | None = None

        while not stop.is_set():
            packet = reader.get_latest(last_sequence, timeout=0.1)
            if packet is not None:
                last_sequence = packet.sequence
                raw_frame = packet.frame
                result = detector.predict(raw_frame)
                roi = roi_state.snapshot()
                detections = tuple(
                    detection
                    for detection in result.detections
                    if _detection_is_inside_roi(
                        detection, roi, raw_frame.shape[1], raw_frame.shape[0]
                    )
                )
                inference_ms = result.inference_ms
                now = time.monotonic()
                if previous_frame_at is not None:
                    instantaneous_fps = 1.0 / max(now - previous_frame_at, 1e-9)
                    fps = instantaneous_fps if fps == 0.0 else 0.9 * fps + 0.1 * instantaneous_fps
                previous_frame_at = now

            roi = roi_state.snapshot()
            canvas = render_detector_frame(
                raw_frame,
                detections,
                roi,
                fps=fps,
                inference_ms=inference_ms,
                stream_connected=reader.status().connected,
                redis_connected=subscriber.status().connected,
                task_id=config.task_id,
            )
            cv2.imshow(config.window_name, canvas)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27) or _window_was_closed(config.window_name):
                stop.set()
    except cv2.error as error:
        raise RuntimeError(
            "OpenCV could not create or update a GUI window; run detector in a desktop session"
        ) from error
    finally:
        stop.set()
        reader.close()
        subscriber.close()
        cv2.destroyAllWindows()
        _restore_signal_handlers(previous_signal_handlers)
        LOGGER.info("Detector stopped")


def _detection_is_inside_roi(
    detection: Detection,
    roi: RoiUpdate | None,
    frame_width: int,
    frame_height: int,
) -> bool:
    """判断检测框中心点是否落在当前激活的 ROI 多边形内。

    先将检测框坐标归一化到 [0, 1] 区间，再做点内多边形（point-in-polygon）
    判断；未设置 ROI 时所有检测均视为在区域内。
    """

    if roi is None:
        return True
    x1, y1, x2, y2 = detection.bbox
    normalized_bbox = (
        x1 / frame_width,
        y1 / frame_height,
        x2 / frame_width,
        y2 / frame_height,
    )
    return bbox_center_is_inside_roi(normalized_bbox, roi)


def _window_was_closed(window_name: str) -> bool:
    """判断 OpenCV 窗口是否已被用户关闭。

    窗口缺失或被销毁时会抛出 ``cv2.error``，此时按“已关闭”处理，
    以便主循环优雅退出。
    """

    try:
        return cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1
    except cv2.error:
        return True


def _install_signal_handlers(
    stop: threading.Event,
) -> dict[signal.Signals, signal.Handlers]:
    """安装 SIGINT/SIGTERM 信号处理器，触发时设置 ``stop`` 事件。

    仅当在主线程（main thread）中被调用时才会注册，因为信号处理器
    必须注册在主线程。返回被替换前的旧处理器，便于调用方恢复。
    """

    previous: dict[signal.Signals, signal.Handlers] = {}

    def request_stop(_signum: int, _frame: object) -> None:
        stop.set()

    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.getsignal(signum)
            signal.signal(signum, request_stop)
    return previous


def _restore_signal_handlers(
    previous: dict[signal.Signals, signal.Handlers],
) -> None:
    """恢复 :func:`_install_signal_handlers` 保存的原始信号处理器。"""

    for signum, handler in previous.items():
        signal.signal(signum, handler)
