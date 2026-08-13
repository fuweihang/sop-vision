"""OpenCV rendering for the detector demo."""

from __future__ import annotations

import cv2
import numpy as np

from algorithm.algorithms.object_detection.yolo import Detection
from algorithm.common.roi import RoiUpdate, normalized_points_to_pixels

GREEN = (64, 220, 64)
YELLOW = (0, 220, 255)
WHITE = (245, 245, 245)
RED = (64, 64, 235)
DARK = (24, 24, 24)


def render_detector_frame(
    frame: np.ndarray,
    detections: tuple[Detection, ...],
    roi: RoiUpdate | None,
    *,
    fps: float,
    inference_ms: float,
    stream_connected: bool,
    redis_connected: bool,
    task_id: str,
) -> np.ndarray:
    """Return an annotated copy suitable for ``cv2.imshow``."""

    canvas = frame.copy()
    height, width = canvas.shape[:2]

    if roi is not None:
        points = np.asarray(
            normalized_points_to_pixels(roi.points, width, height),
            dtype=np.int32,
        ).reshape((-1, 1, 2))
        overlay = canvas.copy()
        cv2.fillPoly(overlay, [points], YELLOW)
        cv2.addWeighted(overlay, 0.12, canvas, 0.88, 0.0, canvas)
        cv2.polylines(canvas, [points], True, YELLOW, 2, cv2.LINE_AA)
        _put_label(canvas, f"ROI: {roi.roi_id}", tuple(points[0, 0]), YELLOW)

    for detection in detections:
        _draw_detection(canvas, detection)

    lines = (
        f"task={task_id}  objects={len(detections)}  fps={fps:.1f}  infer={inference_ms:.1f}ms",
        f"RTSP: {'connected' if stream_connected else 'reconnecting'}  "
        f"Redis: {'subscribed' if redis_connected else 'reconnecting'}  "
        f"ROI: {'active' if roi is not None else 'full-frame'}",
        "Press q or Esc to quit",
    )
    _draw_status_panel(canvas, lines, stream_connected and redis_connected)
    return canvas


def _draw_detection(frame: np.ndarray, detection: Detection) -> None:
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = (
        int(round(value)) for value in detection.bbox
    )
    x1 = min(max(x1, 0), width - 1)
    y1 = min(max(y1, 0), height - 1)
    x2 = min(max(x2, 0), width - 1)
    y2 = min(max(y2, 0), height - 1)
    cv2.rectangle(frame, (x1, y1), (x2, y2), GREEN, 2, cv2.LINE_AA)
    _put_label(
        frame,
        f"{detection.class_name} {detection.confidence:.2f}",
        (x1, y1),
        GREEN,
    )


def _put_label(
    frame: np.ndarray,
    text: str,
    origin: tuple[int, int],
    color: tuple[int, int, int],
) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.52
    thickness = 1
    (text_width, text_height), baseline = cv2.getTextSize(
        text, font, scale, thickness
    )
    x = max(origin[0], 0)
    y = max(origin[1] - 5, text_height + baseline + 3)
    cv2.rectangle(
        frame,
        (x, y - text_height - baseline - 3),
        (x + text_width + 5, y + baseline),
        color,
        cv2.FILLED,
    )
    cv2.putText(
        frame,
        text,
        (x + 2, y - 2),
        font,
        scale,
        DARK,
        thickness,
        cv2.LINE_AA,
    )


def _draw_status_panel(
    frame: np.ndarray, lines: tuple[str, ...], all_connected: bool
) -> None:
    panel_height = 72
    overlay = frame.copy()
    cv2.rectangle(
        overlay,
        (0, 0),
        (frame.shape[1], min(panel_height, frame.shape[0])),
        DARK,
        cv2.FILLED,
    )
    cv2.addWeighted(overlay, 0.72, frame, 0.28, 0.0, frame)
    status_color = WHITE if all_connected else RED
    for index, line in enumerate(lines):
        cv2.putText(
            frame,
            line,
            (10, 20 + index * 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            status_color if index == 1 else WHITE,
            1,
            cv2.LINE_AA,
        )
