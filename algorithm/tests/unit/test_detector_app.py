from algorithm.algorithms.object_detection.yolo import Detection
from algorithm.common.roi import RoiUpdate
from algorithm.workers.detector.app import _detection_is_inside_roi


def test_detection_uses_normalized_bbox_center() -> None:
    roi = RoiUpdate(
        task_id="detector-demo",
        points=((0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (0.0, 1.0)),
    )
    left = Detection(0, "person", 0.9, (10.0, 10.0, 30.0, 30.0))
    right = Detection(0, "person", 0.9, (70.0, 10.0, 90.0, 30.0))

    assert _detection_is_inside_roi(left, roi, 100, 100)
    assert not _detection_is_inside_roi(right, roi, 100, 100)
    assert _detection_is_inside_roi(right, None, 100, 100)
