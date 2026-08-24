import time
from pathlib import Path

from algorithm.algorithms.object_detection.yolo import Detection, DetectionBatch
from algorithm.common.roi import RoiConfig
from algorithm.workers.detector.app import (
    _detection_is_inside_roi,
    build_frame_detection,
)
from algorithm.workers.detector.config import DetectorConfig


def detector_config(roi: RoiConfig | None = None) -> DetectorConfig:
    return DetectorConfig(
        task_id="detector-001",
        rtsp_url="rtsp://camera/stream",
        redis_url="redis://localhost/0",
        model_path=Path("model.pt"),
        roi=roi,
    )


def test_detection_uses_normalized_bbox_center() -> None:
    roi = RoiConfig(
        points=((0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (0.0, 1.0))
    )
    left = Detection(0, "person", 0.9, (10.0, 10.0, 30.0, 30.0))
    right = Detection(0, "person", 0.9, (70.0, 10.0, 90.0, 30.0))

    assert _detection_is_inside_roi(left, roi, 100, 100)
    assert not _detection_is_inside_roi(right, roi, 100, 100)
    assert _detection_is_inside_roi(right, None, 100, 100)


def test_frame_message_filters_roi_and_normalizes_bbox() -> None:
    roi = RoiConfig(
        points=((0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (0.0, 1.0))
    )
    result = DetectionBatch(
        detections=(
            Detection(0, "person", 0.9, (-5.0, 10.0, 30.0, 120.0)),
            Detection(1, "car", 0.8, (70.0, 10.0, 90.0, 30.0)),
        ),
        inference_ms=12.5,
    )

    message = build_frame_detection(
        detector_config(roi),
        result,
        roi,
        run_id="run-1",
        frame_id=7,
        frame_ts_ms=1234,
        frame_width=100,
        frame_height=100,
        fps=20.0,
    )

    assert message.task_id == "detector-001"
    assert message.schema_version == 2
    assert not {
        "camera_id",
        "source_id",
        "algorithm_id",
        "algorithm_version",
    } & message.model_dump().keys()
    assert message.roi_id == "main"
    assert len(message.objects) == 1
    assert message.objects[0].bbox == (0.0, 0.1, 0.3, 1.0)
    assert message.metrics.inference_ms == 12.5


def test_empty_frame_is_still_a_valid_message() -> None:
    before_publish_ms = time.time_ns() // 1_000_000
    message = build_frame_detection(
        detector_config(),
        DetectionBatch(detections=(), inference_ms=3.0),
        None,
        run_id="run-1",
        frame_id=1,
        frame_ts_ms=1234,
        frame_width=1920,
        frame_height=1080,
        fps=0.0,
    )

    assert message.objects == ()
    assert message.roi_id is None
    assert message.frame_ts_ms == 1234
    assert message.frame_id == 1
    assert message.run_id == "run-1"
    assert message.published_at_ms >= before_publish_ms
