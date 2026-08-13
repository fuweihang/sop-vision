"""供各 Worker 复用的轻量 Ultralytics YOLO 适配层。"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True, slots=True)
class Detection:
    class_id: int
    class_name: str
    confidence: float
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class DetectionBatch:
    detections: tuple[Detection, ...]
    inference_ms: float


class YoloDetector:
    """加载一个模型，并对 OpenCV 帧执行同步推理。"""

    def __init__(
        self,
        model_path: Path,
        *,
        image_size: int = 640,
        confidence: float = 0.25,
        device: str | None = None,
    ) -> None:
        runtime_cache = Path(tempfile.gettempdir()) / "sop-vision"
        runtime_cache.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("MPLCONFIGDIR", str(runtime_cache / "matplotlib"))
        os.environ.setdefault("YOLO_CONFIG_DIR", str(runtime_cache / "ultralytics"))

        # 将重量级导入放在此处，避免拖慢 CLI help 与仅用 ROI 的工具。
        from ultralytics import YOLO

        model_path.parent.mkdir(parents=True, exist_ok=True)
        self._model = YOLO(str(model_path))
        # self._model.export(format='engine', device=0, half=True)
        self._image_size = image_size
        self._confidence = confidence
        self._device = device

    def predict(self, frame: np.ndarray) -> DetectionBatch:
        """对一帧图像执行检测，返回不可变的检测结果。"""

        arguments: dict[str, Any] = {
            "source": frame,
            "imgsz": self._image_size,
            "conf": self._confidence,
            "verbose": False,
        }
        if self._device is not None:
            arguments["device"] = self._device

        result = self._model.predict(**arguments)[0]
        return detections_from_result(result)


def detections_from_result(result: Any) -> DetectionBatch:
    """将 Ultralytics 的推理结果转换为 Worker 持有的不可变值。"""

    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        detections: tuple[Detection, ...] = ()
    else:
        coordinates = boxes.xyxy.cpu().tolist()
        confidences = boxes.conf.cpu().tolist()
        class_ids = boxes.cls.cpu().tolist()
        detections = tuple(
            Detection(
                class_id=int(class_id),
                class_name=_class_name(result.names, int(class_id)),
                confidence=float(confidence),
                bbox=tuple(float(value) for value in bbox),
            )
            for bbox, confidence, class_id in zip(
                coordinates, confidences, class_ids, strict=True
            )
        )

    speed = getattr(result, "speed", None) or {}
    return DetectionBatch(
        detections=detections,
        inference_ms=float(speed.get("inference") or 0.0),
    )


def _class_name(names: dict[int, str] | list[str], class_id: int) -> str:
    """按类别 ID 解析类别名称，未知 ID 回退为数字字符串。"""

    if isinstance(names, dict):
        return str(names.get(class_id, class_id))
    if 0 <= class_id < len(names):
        return str(names[class_id])
    return str(class_id)
