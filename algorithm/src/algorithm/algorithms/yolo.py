"""检测与追踪算法共用的 Ultralytics YOLO 基础能力。"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True, slots=True)
class Detection:
    """单个 YOLO 目标；追踪算法可额外提供 ``track_id``。"""

    class_id: int
    class_name: str
    confidence: float
    bbox: tuple[float, float, float, float]
    # 普通检测没有轨迹编号。字段放在最后并提供默认值，避免破坏现有使用
    # 四个位置参数构造 Detection 的调用。
    track_id: int | None = None


@dataclass(frozen=True, slots=True)
class DetectionBatch:
    """一帧的不可变 YOLO 结果及其推理耗时。"""

    detections: tuple[Detection, ...]
    inference_ms: float


class YoloRuntime:
    """负责模型加载和公共推理参数，不决定执行检测还是追踪。"""

    def __init__(
        self,
        model_path: Path,
        *,
        image_size: int = 640,
        confidence: float = 0.25,
        device: str | None = None,
    ) -> None:
        runtime_cache = Path(tempfile.gettempdir()) / "sop-vision"
        matplotlib_cache = runtime_cache / "matplotlib"
        ultralytics_cache = runtime_cache / "ultralytics"
        matplotlib_cache.mkdir(parents=True, exist_ok=True)
        ultralytics_cache.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("MPLCONFIGDIR", str(matplotlib_cache))
        os.environ.setdefault("YOLO_CONFIG_DIR", str(ultralytics_cache))

        # 重量级导入延迟到真正创建算法实例时，避免拖慢 Daemon 和 CLI help。
        from ultralytics import YOLO

        model_path.parent.mkdir(parents=True, exist_ok=True)
        self._model = YOLO(str(model_path))
        self._image_size = image_size
        self._confidence = confidence
        self._device = device

    def _prediction_arguments(self, frame: np.ndarray) -> dict[str, Any]:
        """构造检测与追踪适配器共用的 Ultralytics 参数。"""

        arguments: dict[str, Any] = {
            "source": frame,
            "imgsz": self._image_size,
            "conf": self._confidence,
            "verbose": False,
        }
        if self._device is not None:
            arguments["device"] = self._device
        return arguments


def detections_from_result(result: Any) -> DetectionBatch:
    """复制 Ultralytics 结果，避免 Worker 长时间持有 Tensor 和模型内部对象。"""

    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        detections: tuple[Detection, ...] = ()
    else:
        coordinates = boxes.xyxy.cpu().tolist()
        confidences = boxes.conf.cpu().tolist()
        class_ids = boxes.cls.cpu().tolist()
        raw_track_ids = getattr(boxes, "id", None)
        # ``Boxes.id`` 只在追踪模式下存在。普通检测结果仍使用同一个类型，
        # track_id 保持 None，发布到 Redis 时会按现有规则省略。
        track_ids = (
            raw_track_ids.cpu().tolist()
            if raw_track_ids is not None
            else [None] * len(coordinates)
        )
        detections = tuple(
            Detection(
                class_id=int(class_id),
                class_name=_class_name(result.names, int(class_id)),
                confidence=float(confidence),
                bbox=tuple(float(value) for value in bbox),
                track_id=int(track_id) if track_id is not None else None,
            )
            for bbox, confidence, class_id, track_id in zip(
                coordinates, confidences, class_ids, track_ids, strict=True
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
