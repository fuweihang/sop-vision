"""目标检测（object detection）实现。"""

from algorithm.algorithms.yolo import Detection

from .detection import YoloDetector

__all__ = ["Detection", "YoloDetector"]
