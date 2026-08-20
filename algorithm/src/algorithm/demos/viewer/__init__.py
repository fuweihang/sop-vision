"""RTSP 与 Redis 检测结果的非同步 Qt 演示 Viewer。"""

from .geometry import ContentRect, fit_content_rect, map_normalized_bbox
from .state import DetectionOverlayState

__all__ = [
    "ContentRect",
    "DetectionOverlayState",
    "fit_content_rect",
    "map_normalized_bbox",
]
