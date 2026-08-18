"""Detector Worker 的本地配置模型。"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from algorithm.common.roi import RoiConfig


class DetectorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(min_length=1)
    camera_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    rtsp_url: str = Field(min_length=1)
    redis_url: str = Field(min_length=1)
    model_path: Path
    image_size: int = Field(default=640, gt=0)
    confidence: float = Field(default=0.5, gt=0.0, le=1.0)
    device: str | None = Field(default="0", min_length=1)
    reconnect_delay_seconds: float = Field(default=2.0, gt=0.0)
    algorithm_id: str = Field(default="yolo_object_detection", min_length=1)
    algorithm_version: str = Field(default="0.1.0", min_length=1)
    roi: RoiConfig | None = None

    @field_validator("model_path", mode="before")
    @classmethod
    def validate_model_path(cls, value: object) -> object:
        if not str(value).strip():
            raise ValueError("model_path must not be empty")
        return value

    @property
    def telemetry_channel(self) -> str:
        return f"vision:telemetry:{self.task_id}"

    @property
    def latest_key(self) -> str:
        return f"vision:task:{self.task_id}:latest"
