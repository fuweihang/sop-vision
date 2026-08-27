"""Camera 用例、状态统计、数据库端口和应用错误的公共导入边界。

此包只公开框架无关的普通 Python 类型，不导出 FastAPI、Pydantic、SQLAlchemy 或 ORM 类型。
API、后台任务和后续用例因此可以复用同一状态规则与端口，而不依赖具体基础设施。
"""

from app.modules.cameras.application.create import (
    CreateCameraCommand,
    CreateCameraResult,
    CreateCameraSourceCommand,
    create_camera,
)
from app.modules.cameras.application.errors import (
    CameraConstraintViolationError,
    CameraConstraintViolationKind,
    CameraNotFoundError,
    CameraPersistenceError,
    CameraPersistenceOperationError,
)
from app.modules.cameras.application.ports import (
    CameraListCriteria,
    CameraRepository,
    CameraUnitOfWork,
)
from app.modules.cameras.application.status import (
    CameraRuntimeSummary,
    CameraStatus,
    summarize_camera_runtime,
)

__all__ = [
    "CameraConstraintViolationError",
    "CameraConstraintViolationKind",
    "CameraListCriteria",
    "CameraNotFoundError",
    "CameraPersistenceError",
    "CameraPersistenceOperationError",
    "CameraRepository",
    "CameraRuntimeSummary",
    "CameraStatus",
    "CameraUnitOfWork",
    "CreateCameraCommand",
    "CreateCameraResult",
    "CreateCameraSourceCommand",
    "create_camera",
    "summarize_camera_runtime",
]
