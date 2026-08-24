"""Camera 应用服务可直接导入的数据库接口和错误类型。

此包只公开 Camera/Source 业务对象相关的接口和普通 Python 异常，不导出 FastAPI、
SQLAlchemy 或 ORM 类型。
这样后续应用服务可以在不知道数据库实现细节的情况下使用真实 Repository 或测试 Fake。
"""

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

__all__ = [
    "CameraConstraintViolationError",
    "CameraConstraintViolationKind",
    "CameraListCriteria",
    "CameraNotFoundError",
    "CameraPersistenceError",
    "CameraPersistenceOperationError",
    "CameraRepository",
    "CameraUnitOfWork",
]
