"""视频类 Worker 共用的输入参数。"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from algorithm.common.roi import RoiConfig


class VideoWorkerConfig(BaseModel):
    """定义 RTSP 视频 Worker 都需要的连接、模型和发布参数。

    具体 Worker 必须各自声明配置子类，保证注册表和 JSON Schema 仍能明确区分
    Worker 类型。公共字段放在这里，避免 Tracker 通过继承 Detector 获取参数。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(title="任务 ID", min_length=1)
    rtsp_url: str = Field(title="RTSP 地址", min_length=1)
    redis_url: str = Field(title="Redis 地址", min_length=1)
    model_path: Path = Field(
        title="模型路径",
        description="绝对路径，或相对于 ALGORITHM_RESOURCE_ROOT 的路径。",
    )
    image_size: int = Field(title="推理图像尺寸", default=640, gt=0)
    confidence: float = Field(title="置信度阈值", default=0.5, gt=0.0, le=1.0)
    device: str | None = Field(
        title="推理设备",
        description="例如 0、cpu；null 表示由推理框架自动选择。",
        default="0",
        min_length=1,
    )
    reconnect_delay_seconds: float = Field(
        title="断线重连间隔（秒）", default=2.0, gt=0.0
    )
    roi: RoiConfig | None = Field(
        title="检测区域",
        description="null 表示检测整个画面。",
        default=None,
    )

    @field_validator("model_path", mode="before")
    @classmethod
    def validate_model_path(cls, value: object) -> object:
        """拒绝空路径，避免模型库把空字符串解释成其他默认资源。"""

        if not str(value).strip():
            raise ValueError("model_path must not be empty")
        return value

    @property
    def telemetry_channel(self) -> str:
        return f"vision:telemetry:{self.task_id}"

    @property
    def latest_key(self) -> str:
        return f"vision:task:{self.task_id}:latest"
