"""Configuration for the detector demo."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import SplitResult, urlsplit, urlunsplit


DEFAULT_RTSP_URL = (
    "rtsp://admin:Ts2026626%23@192.168.13.234:554/Streaming/Channels/201"
)
DEFAULT_REDIS_URL = "redis://127.0.0.1:63793/0"
DEFAULT_TASK_ID = "detector-demo"
DEFAULT_ROI_CHANNEL = f"vision:config:roi:{DEFAULT_TASK_ID}"


def project_root() -> Path:
    """Return the algorithm project root regardless of the current directory."""

    return Path(__file__).resolve().parents[3]


def default_model_path() -> Path:
    return project_root() / "resources" / "models" / "yolo26n.pt"


def redact_url(value: str) -> str:
    """Remove credentials from a URL before it is written to logs."""

    try:
        parsed = urlsplit(value)
    except ValueError:
        return "<invalid-url>"

    if not parsed.hostname:
        return value

    host = parsed.hostname
    if ":" in host:
        host = f"[{host}]"
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    if parsed.username is not None:
        host = f"***:***@{host}"

    return urlunsplit(
        SplitResult(parsed.scheme, host, parsed.path, parsed.query, parsed.fragment)
    )


@dataclass(frozen=True, slots=True)
class DetectorConfig:
    rtsp_url: str = DEFAULT_RTSP_URL
    redis_url: str = DEFAULT_REDIS_URL
    task_id: str = DEFAULT_TASK_ID
    roi_channel: str = DEFAULT_ROI_CHANNEL
    model_path: Path = default_model_path()
    image_size: int = 640
    confidence: float = 0.5
    # Ultralytics accepts a CUDA device index as a string. Default to the first
    # GPU so the detector never silently falls back to CPU.
    device: str | None = "0"
    reconnect_delay_seconds: float = 2.0
    window_name: str = "SOP Vision - Detector Demo"

    def __post_init__(self) -> None:
        if not self.rtsp_url:
            raise ValueError("rtsp_url must not be empty")
        if not self.redis_url:
            raise ValueError("redis_url must not be empty")
        if not self.task_id:
            raise ValueError("task_id must not be empty")
        if not self.roi_channel:
            raise ValueError("roi_channel must not be empty")
        if self.image_size <= 0:
            raise ValueError("image_size must be positive")
        if not 0.0 < self.confidence <= 1.0:
            raise ValueError("confidence must be in (0, 1]")
        if self.reconnect_delay_seconds <= 0:
            raise ValueError("reconnect_delay_seconds must be positive")

    @classmethod
    def from_environment(cls) -> DetectorConfig:
        """Build configuration from DETECTOR_* variables and code defaults."""

        default = cls()
        task_id = os.getenv("DETECTOR_TASK_ID", default.task_id)
        roi_channel = os.getenv("DETECTOR_ROI_CHANNEL")
        if roi_channel is None:
            roi_channel = (
                default.roi_channel
                if task_id == default.task_id
                else f"vision:config:roi:{task_id}"
            )
        device = os.getenv("DETECTOR_DEVICE", default.device)
        if device is not None and device.lower() == "auto":
            device = None

        return replace(
            default,
            rtsp_url=os.getenv("DETECTOR_RTSP_URL", default.rtsp_url),
            redis_url=os.getenv("DETECTOR_REDIS_URL", default.redis_url),
            task_id=task_id,
            roi_channel=roi_channel,
            model_path=Path(os.getenv("DETECTOR_MODEL_PATH", str(default.model_path))),
            image_size=int(os.getenv("DETECTOR_IMAGE_SIZE", default.image_size)),
            confidence=float(os.getenv("DETECTOR_CONFIDENCE", default.confidence)),
            device=device,
            reconnect_delay_seconds=float(
                os.getenv(
                    "DETECTOR_RECONNECT_DELAY_SECONDS",
                    default.reconnect_delay_seconds,
                )
            ),
        )
