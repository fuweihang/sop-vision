"""本地配置驱动的 ROI 模型与几何辅助函数。"""

from __future__ import annotations

import math
import threading

from pydantic import BaseModel, ConfigDict, Field, model_validator

Point = tuple[float, float]
Bbox = tuple[float, float, float, float]


class RoiConfig(BaseModel):
    """一个检测任务的单个归一化 ROI 多边形。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    roi_id: str = Field(default="main", min_length=1)
    points: tuple[Point, ...]

    @model_validator(mode="after")
    def validate_polygon(self) -> RoiConfig:
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


class RoiState:
    """线程安全的 ROI 快照；当前 Worker 仅在启动时设置一次。"""

    def __init__(self, initial: RoiConfig | None = None) -> None:
        self._lock = threading.Lock()
        self._active = initial

    def replace(self, roi: RoiConfig | None) -> None:
        """原子替换当前 ROI。"""

        with self._lock:
            self._active = roi

    def snapshot(self) -> RoiConfig | None:
        """返回当前激活的 ROI 快照；未设置时为 ``None``。"""

        with self._lock:
            return self._active


def bbox_center_is_inside_roi(bbox: Bbox, roi: RoiConfig | None) -> bool:
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
