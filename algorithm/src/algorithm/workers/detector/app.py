"""无界面 Detector Worker 的生命周期与组件编排。"""

from __future__ import annotations

import logging
import signal
import threading
import time
import uuid
from collections.abc import Callable

from algorithm.algorithms.object_detection.yolo import (
    Detection,
    DetectionBatch,
    YoloDetector,
)
from algorithm.common.config import redact_url
from algorithm.common.redis_telemetry import RedisTelemetryPublisher
from algorithm.common.roi import RoiConfig, RoiState, bbox_center_is_inside_roi
from algorithm.common.rtsp import LatestFrameReader
from algorithm.contracts.detection import (
    DetectionMetrics,
    DetectionObject,
    FrameDetection,
)
from algorithm.workers.base import StopEvent

from .config import DetectorConfig

LOGGER = logging.getLogger(__name__)


def run_detector(
    config: DetectorConfig,
    *,
    stop_event: StopEvent | None = None,
    ready_callback: Callable[[], None] | None = None,
) -> None:
    """持续拉流、推理并发布元数据，直到收到停止请求。"""

    stop = stop_event or threading.Event()
    previous_signal_handlers = _install_signal_handlers(stop)
    roi_state = RoiState(config.roi)
    publisher = RedisTelemetryPublisher(
        config.redis_url,
        config.telemetry_channel,
        config.latest_key,
        reconnect_delay_seconds=config.reconnect_delay_seconds,
    )
    reader = LatestFrameReader(
        config.rtsp_url,
        reconnect_delay_seconds=config.reconnect_delay_seconds,
    )

    LOGGER.info("Starting detector task %s", config.task_id)
    LOGGER.info("RTSP source: %s", redact_url(config.rtsp_url))
    LOGGER.info("Telemetry channel: %s", config.telemetry_channel)
    LOGGER.info("Loading YOLO model from %s", config.model_path)
    LOGGER.info("YOLO inference device: %s", config.device or "auto")

    publisher.start()
    try:
        detector = YoloDetector(
            config.model_path,
            image_size=config.image_size,
            confidence=config.confidence,
            device=config.device,
        )
        reader.start()
        if ready_callback is not None:
            ready_callback()

        last_sequence = 0
        fps = 0.0
        previous_frame_at: float | None = None
        run_id = str(uuid.uuid4())

        while not stop.is_set():
            packet = reader.get_latest(last_sequence, timeout=0.1)
            if packet is None:
                continue

            last_sequence = packet.sequence
            result = detector.predict(packet.frame)
            now = time.monotonic()
            if previous_frame_at is not None:
                instantaneous_fps = 1.0 / max(now - previous_frame_at, 1e-9)
                fps = (
                    instantaneous_fps
                    if fps == 0.0
                    else 0.9 * fps + 0.1 * instantaneous_fps
                )
            previous_frame_at = now
            height, width = packet.frame.shape[:2]
            message = build_frame_detection(
                config,
                result,
                roi_state.snapshot(),
                run_id=run_id,
                frame_id=packet.sequence,
                frame_ts_ms=round(packet.captured_at * 1000),
                frame_width=width,
                frame_height=height,
                fps=fps,
            )
            publisher.submit(message)
    finally:
        stop.set()
        reader.close()
        publisher.close()
        _restore_signal_handlers(previous_signal_handlers)
        LOGGER.info("Detector stopped")


def build_frame_detection(
    config: DetectorConfig,
    result: DetectionBatch,
    roi: RoiConfig | None,
    *,
    run_id: str,
    frame_id: int,
    frame_ts_ms: int,
    frame_width: int,
    frame_height: int,
    fps: float,
) -> FrameDetection:
    """过滤 ROI 并将一帧结果转换为稳定的 Redis 消息。"""

    objects = tuple(
        DetectionObject(
            class_id=detection.class_id,
            class_name=detection.class_name,
            confidence=detection.confidence,
            bbox=_normalized_bbox(detection, frame_width, frame_height),
        )
        for detection in result.detections
        if _detection_is_inside_roi(detection, roi, frame_width, frame_height)
    )
    return FrameDetection(
        task_id=config.task_id,
        camera_id=config.camera_id,
        source_id=config.source_id,
        algorithm_id=config.algorithm_id,
        algorithm_version=config.algorithm_version,
        run_id=run_id,
        frame_id=frame_id,
        frame_ts_ms=frame_ts_ms,
        published_at_ms=time.time_ns() // 1_000_000,
        source_width=frame_width,
        source_height=frame_height,
        roi_id=roi.roi_id if roi is not None else None,
        objects=objects,
        metrics=DetectionMetrics(inference_ms=result.inference_ms, fps=fps),
    )


def _detection_is_inside_roi(
    detection: Detection,
    roi: RoiConfig | None,
    frame_width: int,
    frame_height: int,
) -> bool:
    """判断检测框中心点是否落在当前激活的 ROI 多边形内。

    先将检测框坐标归一化到 [0, 1] 区间，再做点内多边形（point-in-polygon）
    判断；未设置 ROI 时所有检测均视为在区域内。
    """

    if roi is None:
        return True
    normalized_bbox = _normalized_bbox(detection, frame_width, frame_height)
    return bbox_center_is_inside_roi(normalized_bbox, roi)


def _normalized_bbox(
    detection: Detection,
    frame_width: int,
    frame_height: int,
) -> tuple[float, float, float, float]:
    if frame_width <= 0 or frame_height <= 0:
        raise ValueError("frame dimensions must be positive")
    x1, y1, x2, y2 = detection.bbox
    return (
        min(max(x1 / frame_width, 0.0), 1.0),
        min(max(y1 / frame_height, 0.0), 1.0),
        min(max(x2 / frame_width, 0.0), 1.0),
        min(max(y2 / frame_height, 0.0), 1.0),
    )


def _install_signal_handlers(
    stop: StopEvent,
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
