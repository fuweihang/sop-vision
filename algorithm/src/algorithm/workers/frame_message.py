"""检测与追踪 Worker 共用的帧消息构建。"""

from __future__ import annotations

import time
from typing import Protocol

from algorithm.algorithms.yolo import Detection, DetectionBatch
from algorithm.common.roi import RoiConfig, bbox_center_is_inside_roi
from algorithm.contracts.detection import (
    DetectionMetrics,
    DetectionObject,
    FrameDetection,
)


class FrameWorkerConfig(Protocol):
    """构建帧消息时真正需要的最小配置接口。"""

    task_id: str


def build_frame_message(
    config: FrameWorkerConfig,
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
    """过滤 ROI，并把检测或追踪结果转换为 Redis 帧消息。

    ROI 只影响发布结果，不会修改传给追踪器的检测集合。因此目标暂时离开 ROI
    时 ByteTrack 仍能维护它的内部状态，重新进入后有机会继续使用原轨迹编号。
    """

    objects = tuple(
        DetectionObject(
            class_id=detection.class_id,
            class_name=detection.class_name,
            confidence=detection.confidence,
            bbox=normalized_bbox(detection, frame_width, frame_height),
            track_id=detection.track_id,
        )
        for detection in result.detections
        if detection_is_inside_roi(detection, roi, frame_width, frame_height)
    )
    return FrameDetection(
        task_id=config.task_id,
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


def detection_is_inside_roi(
    detection: Detection,
    roi: RoiConfig | None,
    frame_width: int,
    frame_height: int,
) -> bool:
    """按归一化检测框中心点判断目标是否位于当前 ROI。"""

    if roi is None:
        return True
    bbox = normalized_bbox(detection, frame_width, frame_height)
    return bbox_center_is_inside_roi(bbox, roi)


def normalized_bbox(
    detection: Detection,
    frame_width: int,
    frame_height: int,
) -> tuple[float, float, float, float]:
    """把像素坐标框裁剪并归一化到帧消息要求的 ``[0, 1]`` 区间。"""

    if frame_width <= 0 or frame_height <= 0:
        raise ValueError("帧宽度和高度必须大于 0")
    x1, y1, x2, y2 = detection.bbox
    return (
        min(max(x1 / frame_width, 0.0), 1.0),
        min(max(y1 / frame_height, 0.0), 1.0),
        min(max(x2 / frame_width, 0.0), 1.0),
        min(max(y2 / frame_height, 0.0), 1.0),
    )
