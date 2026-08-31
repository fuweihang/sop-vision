"""基于 Ultralytics YOLO 的目标检测适配器。"""

from __future__ import annotations

import numpy as np

from algorithm.algorithms.yolo import (
    DetectionBatch,
    YoloRuntime,
    detections_from_result,
)


class YoloDetector(YoloRuntime):
    """加载一个 YOLO 模型，并对 OpenCV 帧执行同步检测。"""

    def predict(self, frame: np.ndarray) -> DetectionBatch:
        """对一帧图像执行检测，返回不持有 Tensor 的结果。"""

        result = self._model.predict(**self._prediction_arguments(frame))[0]
        return detections_from_result(result)
