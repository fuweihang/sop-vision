"""ROI 消息模型、状态管理与几何辅助函数。"""

from __future__ import annotations

import math
import threading
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Point = tuple[float, float]
Bbox = tuple[float, float, float, float]


class RoiUpdate(BaseModel):
    """从 Redis Pub/Sub 接收的带版本号（versioned）ROI 更新。"""

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
    """当更新消息指向其他 detector 任务时抛出。"""


def parse_roi_update(payload: str | bytes, expected_task_id: str) -> RoiUpdate:
    """解析 ROI 更新消息，并校验其目标任务是否匹配。"""

    update = RoiUpdate.model_validate_json(payload)
    if update.task_id != expected_task_id:
        raise RoiTaskMismatch(
            f"ROI task_id {update.task_id!r} does not match {expected_task_id!r}"
        )
    return update


class RoiState:
    """线程安全（thread-safe）的最近一次有效 ROI 快照。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: RoiUpdate | None = None

    def apply_payload(self, payload: str | bytes, expected_task_id: str) -> RoiUpdate:
        """解析并原子化应用一条 ROI 更新，返回解析后的更新对象。"""

        update = parse_roi_update(payload, expected_task_id)
        with self._lock:
            self._active = update if update.enabled else None
        return update

    def snapshot(self) -> RoiUpdate | None:
        """返回当前激活的 ROI 快照；未设置时为 ``None``。"""

        with self._lock:
            return self._active


def bbox_center_is_inside_roi(bbox: Bbox, roi: RoiUpdate | None) -> bool:
    """当 bbox 中心位于激活多边形内部或边界上时返回 True。"""

    if roi is None:
        return True
    x1, y1, x2, y2 = bbox
    center = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
    return point_in_polygon(center, roi.points)


def point_in_polygon(point: Point, polygon: tuple[Point, ...]) -> bool:
    """射线法（ray-casting）判断，多边形边上的点视为在内部。"""

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
    """将归一化的 [0, 1] 坐标点转换为像素坐标。"""

    if width <= 0 or height <= 0:
        raise ValueError("frame dimensions must be positive")
    return tuple(
        (round(x * (width - 1)), round(y * (height - 1))) for x, y in points
    )


def _signed_area(points: tuple[Point, ...]) -> float:
    """计算多边形有向面积（signed area）。"""

    return 0.5 * sum(
        x1 * y2 - x2 * y1
        for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1])
    )


def _point_on_segment(point: Point, start: Point, end: Point) -> bool:
    """判断点是否落在线段上（含端点）。"""

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
