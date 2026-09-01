"""无界面 Tracker Worker 的生命周期与组件编排。"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable

from algorithm.algorithms.object_tracking.bytetrack import YoloTracker
from algorithm.common.config import redact_url
from algorithm.common.redis_telemetry import RedisTelemetryPublisher
from algorithm.common.roi import RoiState
from algorithm.common.rtsp import LatestFrameReader
from algorithm.workers.base import (
    StopEvent,
    install_stop_signal_handlers,
    restore_signal_handlers,
)
from algorithm.workers.frame_message import build_frame_message

from .config import TrackerConfig

LOGGER = logging.getLogger(__name__)


def run_tracker(
    config: TrackerConfig,
    *,
    stop_event: StopEvent | None = None,
    ready_callback: Callable[[], None] | None = None,
) -> None:
    """持续拉流、追踪并发布带 ``track_id`` 的检测消息，直到收到停止请求。"""

    stop = stop_event or threading.Event()
    previous_signal_handlers = install_stop_signal_handlers(stop)
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

    LOGGER.info("正在启动追踪任务 %s", config.task_id)
    LOGGER.info("RTSP 来源：%s", redact_url(config.rtsp_url))
    LOGGER.info("遥测频道：%s", config.telemetry_channel)
    LOGGER.info("正在加载 YOLO 模型：%s", config.model_path)
    LOGGER.info("YOLO 推理设备：%s", config.device or "自动选择")
    LOGGER.info("追踪配置：bytetrack.yaml")

    publisher.start()
    try:
        tracker = YoloTracker(
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
            result = tracker.track(packet.frame)
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
            message = build_frame_message(
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
        restore_signal_handlers(previous_signal_handlers)
        LOGGER.info("追踪任务已停止")
