"""与 Qt 无关的视频画面和归一化检测框映射。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContentRect:
    """视频等比缩放后在显示区域内实际占用的矩形。"""

    x: float
    y: float
    width: float
    height: float


def fit_content_rect(
    view_width: float,
    view_height: float,
    source_width: float,
    source_height: float,
) -> ContentRect:
    """计算保持宽高比并居中显示时的视频内容区域。"""

    if min(view_width, view_height, source_width, source_height) <= 0:
        return ContentRect(0.0, 0.0, 0.0, 0.0)
    scale = min(view_width / source_width, view_height / source_height)
    width = min(view_width, source_width * scale)
    height = min(view_height, source_height * scale)
    return ContentRect(
        x=max(0.0, (view_width - width) / 2.0),
        y=max(0.0, (view_height - height) / 2.0),
        width=width,
        height=height,
    )


def map_normalized_bbox(
    bbox: tuple[float, float, float, float],
    content: ContentRect,
) -> tuple[float, float, float, float]:
    """把归一化 bbox 映射为显示区域坐标，并裁剪到视频内容范围。"""

    x1, y1, x2, y2 = (min(max(value, 0.0), 1.0) for value in bbox)
    left = content.x + min(x1, x2) * content.width
    top = content.y + min(y1, y2) * content.height
    right = content.x + max(x1, x2) * content.width
    bottom = content.y + max(y1, y2) * content.height
    return left, top, right, bottom


def map_normalized_polygon(
    points: tuple[tuple[float, float], ...],
    content: ContentRect,
) -> tuple[tuple[float, float], ...]:
    """把归一化多边形顶点映射到视频内容区域，并裁剪到内容边界。"""

    return tuple(
        (
            content.x + min(max(x, 0.0), 1.0) * content.width,
            content.y + min(max(y, 0.0), 1.0) * content.height,
        )
        for x, y in points
    )
