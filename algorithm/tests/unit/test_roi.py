import pytest
from pydantic import ValidationError

from algorithm.common.roi import (
    RoiState,
    RoiTaskMismatch,
    RoiUpdate,
    bbox_center_is_inside_roi,
    normalized_points_to_pixels,
    parse_roi_update,
    point_in_polygon,
)


VALID_PAYLOAD = """{
  "schema_version": 1,
  "type": "roi_update",
  "task_id": "detector-demo",
  "roi_id": "main",
  "enabled": true,
  "points": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
}"""


def test_parse_valid_roi() -> None:
    update = parse_roi_update(VALID_PAYLOAD, "detector-demo")

    assert update.enabled is True
    assert len(update.points) == 4


@pytest.mark.parametrize(
    "points",
    [
        [(0.1, 0.1), (0.9, 0.1)],
        [(0.1, 0.1), (1.1, 0.1), (0.9, 0.9)],
        [(0.1, 0.1), (0.5, 0.5), (0.9, 0.9)],
        [(0.1, 0.1), (0.1, 0.1), (0.9, 0.9)],
    ],
)
def test_rejects_invalid_polygon(points) -> None:
    with pytest.raises(ValidationError):
        RoiUpdate(task_id="detector-demo", enabled=True, points=points)


def test_disabled_roi_requires_empty_points() -> None:
    with pytest.raises(ValidationError):
        RoiUpdate(
            task_id="detector-demo",
            enabled=False,
            points=((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)),
        )


def test_task_mismatch_does_not_replace_state() -> None:
    state = RoiState()
    expected = state.apply_payload(VALID_PAYLOAD, "detector-demo")

    with pytest.raises(RoiTaskMismatch):
        state.apply_payload(
            VALID_PAYLOAD.replace("detector-demo", "another-task"),
            "detector-demo",
        )

    assert state.snapshot() == expected


def test_disabled_update_clears_state() -> None:
    state = RoiState()
    state.apply_payload(VALID_PAYLOAD, "detector-demo")

    state.apply_payload(
        '{"schema_version":1,"type":"roi_update","task_id":"detector-demo",'
        '"roi_id":"main","enabled":false,"points":[]}',
        "detector-demo",
    )

    assert state.snapshot() is None


def test_point_and_bbox_center_include_polygon_boundary() -> None:
    roi = RoiUpdate(
        task_id="detector-demo",
        points=((0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)),
    )

    assert point_in_polygon((0.25, 0.5), roi.points)
    assert bbox_center_is_inside_roi((0.4, 0.4, 0.6, 0.6), roi)
    assert not bbox_center_is_inside_roi((0.0, 0.0, 0.2, 0.2), roi)


def test_normalized_points_convert_to_frame_pixels() -> None:
    assert normalized_points_to_pixels(((0.0, 0.0), (1.0, 1.0)), 1920, 1080) == (
        (0, 0),
        (1919, 1079),
    )
