"""ROI message schema, state management, and geometry helpers."""

from __future__ import annotations

import math
import threading
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Point = tuple[float, float]
Bbox = tuple[float, float, float, float]


class RoiUpdate(BaseModel):
    """Versioned ROI update accepted from Redis Pub/Sub."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    type: Literal["roi_update"] = "roi_update"
    task_id: str = Field(min_length=1)
    roi_id: str = Field(default="main", min_length=1)
    enabled: bool = True
    points: tuple[Point, ...]

    @model_validator(mode="after")
    def validate_polygon(self) -> RoiUpdate:
        if not self.enabled:
            if self.points:
                raise ValueError("a disabled ROI must have an empty points array")
            return self

        if len(self.points) < 3:
            raise ValueError("an enabled ROI requires at least three points")
        if any(
            not math.isfinite(value) or not 0.0 <= value <= 1.0
            for point in self.points
            for value in point
        ):
            raise ValueError("ROI coordinates must be finite values in [0, 1]")
        if len(set(self.points)) < 3:
            raise ValueError("an enabled ROI requires at least three distinct points")
        if math.isclose(_signed_area(self.points), 0.0, abs_tol=1e-12):
            raise ValueError("ROI polygon must have a non-zero area")
        return self


class RoiTaskMismatch(ValueError):
    """Raised when an update is addressed to another detector task."""


def parse_roi_update(payload: str | bytes, expected_task_id: str) -> RoiUpdate:
    update = RoiUpdate.model_validate_json(payload)
    if update.task_id != expected_task_id:
        raise RoiTaskMismatch(
            f"ROI task_id {update.task_id!r} does not match {expected_task_id!r}"
        )
    return update


class RoiState:
    """Thread-safe last-valid ROI snapshot."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: RoiUpdate | None = None

    def apply_payload(self, payload: str | bytes, expected_task_id: str) -> RoiUpdate:
        update = parse_roi_update(payload, expected_task_id)
        with self._lock:
            self._active = update if update.enabled else None
        return update

    def snapshot(self) -> RoiUpdate | None:
        with self._lock:
            return self._active


def bbox_center_is_inside_roi(bbox: Bbox, roi: RoiUpdate | None) -> bool:
    """Return True when a bbox center is inside or on the active polygon."""

    if roi is None:
        return True
    x1, y1, x2, y2 = bbox
    center = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
    return point_in_polygon(center, roi.points)


def point_in_polygon(point: Point, polygon: tuple[Point, ...]) -> bool:
    """Ray-casting test that treats polygon edges as inside."""

    x, y = point
    inside = False
    previous = polygon[-1]
    for current in polygon:
        x1, y1 = previous
        x2, y2 = current
        if _point_on_segment(point, previous, current):
            return True
        if (y1 > y) != (y2 > y):
            intersection_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < intersection_x:
                inside = not inside
        previous = current
    return inside


def normalized_points_to_pixels(
    points: tuple[Point, ...], width: int, height: int
) -> tuple[tuple[int, int], ...]:
    if width <= 0 or height <= 0:
        raise ValueError("frame dimensions must be positive")
    return tuple(
        (round(x * (width - 1)), round(y * (height - 1))) for x, y in points
    )


def _signed_area(points: tuple[Point, ...]) -> float:
    return 0.5 * sum(
        x1 * y2 - x2 * y1
        for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1])
    )


def _point_on_segment(point: Point, start: Point, end: Point) -> bool:
    x, y = point
    x1, y1 = start
    x2, y2 = end
    cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
    if not math.isclose(cross, 0.0, abs_tol=1e-9):
        return False
    return (
        min(x1, x2) - 1e-9 <= x <= max(x1, x2) + 1e-9
        and min(y1, y2) - 1e-9 <= y <= max(y1, y2) + 1e-9
    )
