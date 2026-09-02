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
from app.modules.cameras.application.detail import CameraDetailResult, get_camera_detail
from app.modules.cameras.application.errors import (
    CameraAggregateInvalidError,
    CameraConstraintViolationError,
    CameraConstraintViolationKind,
    CameraListAggregateInvalidError,
    CameraNotFoundError,
    CameraPersistenceError,
    CameraPersistenceOperationError,
)
from app.modules.cameras.application.listing import (
    CameraListItemResult,
    CameraListResult,
    list_cameras,
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
from app.modules.cameras.application.update import (
    UpdateCameraCommand,
    UpdateCameraResult,
    UpdateCameraSourceCommand,
    update_camera,
)

__all__ = [
    "CameraAggregateInvalidError",
    "CameraConstraintViolationError",
    "CameraConstraintViolationKind",
    "CameraDetailResult",
    "CameraListCriteria",
    "CameraListAggregateInvalidError",
    "CameraListItemResult",
    "CameraListResult",
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
    "UpdateCameraCommand",
    "UpdateCameraResult",
    "UpdateCameraSourceCommand",
    "create_camera",
    "get_camera_detail",
    "list_cameras",
    "summarize_camera_runtime",
    "update_camera",
]
