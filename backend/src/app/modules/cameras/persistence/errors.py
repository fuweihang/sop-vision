"""Camera Repository 的稳定持久化错误。"""


class CameraPersistenceError(Exception):
    """可由后续应用层精确解释的持久化前置条件错误。"""

    code = "CAMERA_PERSISTENCE_ERROR"


class CameraNotFoundError(CameraPersistenceError):
    """待锁定的 Camera 不存在。"""

    code = "CAMERA_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Camera 不存在。")


class SourceNotOwnedByCameraError(CameraPersistenceError):
    """Source 不存在或不属于指定 Camera。"""

    code = "SOURCE_NOT_OWNED_BY_CAMERA"

    def __init__(self) -> None:
        super().__init__("Source 不存在或不属于当前 Camera。")


class InvalidCameraAggregateError(CameraPersistenceError):
    """待持久化聚合不满足最小跨表不变量。"""

    code = "INVALID_CAMERA_AGGREGATE"


class LastCameraSourceError(CameraPersistenceError):
    """调用方试图删除 Camera 的最后一路 Source。"""

    code = "LAST_CAMERA_SOURCE"

    def __init__(self) -> None:
        super().__init__("Camera 必须至少保留一路 Source。")


class DefaultSourceReplacementRequiredError(CameraPersistenceError):
    """删除当前默认 Source 时没有提供合法替代项。"""

    code = "DEFAULT_SOURCE_REPLACEMENT_REQUIRED"

    def __init__(self) -> None:
        super().__init__("删除默认 Source 前必须指定同一 Camera 的替代默认 Source。")
