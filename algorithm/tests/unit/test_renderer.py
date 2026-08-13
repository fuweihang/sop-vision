import numpy as np

from algorithm.algorithms.object_detection.yolo import Detection
from algorithm.common.roi import RoiUpdate
from algorithm.workers.detector.renderer import render_detector_frame


def test_renderer_draws_detection_roi_and_status_without_mutating_input() -> None:
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    original = frame.copy()
    detection = Detection(0, "person", 0.93, (80.0, 60.0, 180.0, 210.0))
    roi = RoiUpdate(
        task_id="detector-demo",
        points=((0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)),
    )

    rendered = render_detector_frame(
        frame,
        (detection,),
        roi,
        fps=25.0,
        inference_ms=12.0,
        stream_connected=True,
        redis_connected=True,
        task_id="detector-demo",
    )

    assert np.array_equal(frame, original)
    assert not np.array_equal(rendered, original)
