"""Cameras MVP 框架无关的领域模型与规则。"""

from app.modules.cameras.domain.errors import (
    CameraAggregateCorruptedError,
    CameraDomainError,
    CameraDomainErrorCode,
    CameraFieldError,
    CameraValidationError,
)
from app.modules.cameras.domain.models import (
    Camera,
    CameraId,
    CameraSource,
    CameraSourceChange,
    NewCameraSource,
    SourceId,
)
from app.modules.cameras.domain.ports import Clock, IdGenerator, SystemClock, Uuid4Generator
from app.modules.cameras.domain.values import (
    CameraCredentials,
    SecretValue,
    build_rtsp_url,
    create_credentials,
    normalize_name,
    normalize_url_suffix,
    validate_ipv4,
    validate_rtsp_port,
)

__all__ = [
    "Camera",
    "CameraAggregateCorruptedError",
    "CameraCredentials",
    "CameraDomainError",
    "CameraDomainErrorCode",
    "CameraFieldError",
    "CameraId",
    "CameraSource",
    "CameraSourceChange",
    "CameraValidationError",
    "Clock",
    "IdGenerator",
    "NewCameraSource",
    "SecretValue",
    "SourceId",
    "SystemClock",
    "Uuid4Generator",
    "build_rtsp_url",
    "create_credentials",
    "normalize_name",
    "normalize_url_suffix",
    "validate_ipv4",
    "validate_rtsp_port",
]
