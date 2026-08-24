"""AIWorker 发布到 Redis 的检测结果契约。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DetectionObject(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    class_id: int
    class_name: str
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: tuple[float, float, float, float]
    track_id: int | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("bbox")
    @classmethod
    def validate_bbox(
        cls, bbox: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
        if any(not 0.0 <= value <= 1.0 for value in bbox):
            raise ValueError("bbox coordinates must be in [0, 1]")
        x1, y1, x2, y2 = bbox
        if x2 < x1 or y2 < y1:
            raise ValueError("bbox must use [x1, y1, x2, y2] ordering")
        return bbox


class DetectionMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    inference_ms: float = Field(ge=0.0)
    fps: float = Field(ge=0.0)


class FrameDetection(BaseModel):
    """一个已完成推理的视频帧及其目标检测元数据。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[2] = 2
    type: Literal["frame_detection"] = "frame_detection"
    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    frame_id: int = Field(ge=1)
    frame_ts_ms: int = Field(ge=0)
    published_at_ms: int = Field(ge=0)
    source_width: int = Field(gt=0)
    source_height: int = Field(gt=0)
    roi_id: str | None = None
    objects: tuple[DetectionObject, ...]
    metrics: DetectionMetrics
