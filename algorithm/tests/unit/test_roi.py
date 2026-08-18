import pytest
from pydantic import ValidationError

from algorithm.common.roi import (
    RoiConfig,
    RoiState,
    bbox_center_is_inside_roi,
    point_in_polygon,
)


def test_valid_roi_can_initialize_state() -> None:
    roi = RoiConfig(
        points=((0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9))
    )

    assert RoiState(roi).snapshot() == roi


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
        RoiConfig(points=points)


def test_state_can_clear_roi() -> None:
    state = RoiState(
        RoiConfig(points=((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)))
    )

    state.replace(None)

    assert state.snapshot() is None


def test_point_and_bbox_center_include_polygon_boundary() -> None:
    roi = RoiConfig(
        points=((0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75))
    )

    assert point_in_polygon((0.25, 0.5), roi.points)
    assert bbox_center_is_inside_roi((0.4, 0.4, 0.6, 0.6), roi)
    assert not bbox_center_is_inside_roi((0.0, 0.0, 0.2, 0.2), roi)
