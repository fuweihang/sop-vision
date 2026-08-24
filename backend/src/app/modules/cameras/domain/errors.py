"""Cameras 领域层可稳定映射、且不会携带原始输入的错误。"""

from dataclasses import dataclass
from enum import StrEnum


class CameraDomainErrorCode(StrEnum):
    """已由 Cameras MVP 文档冻结的字段错误 code。"""

    REQUIRED = "REQUIRED"
    STRING_TOO_LONG = "STRING_TOO_LONG"
    INVALID_IP_ADDRESS = "INVALID_IP_ADDRESS"
    INVALID_UUID = "INVALID_UUID"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    SOURCE_REQUIRED = "SOURCE_REQUIRED"
    DEFAULT_SOURCE_REQUIRED = "DEFAULT_SOURCE_REQUIRED"
    MULTIPLE_DEFAULT_SOURCES = "MULTIPLE_DEFAULT_SOURCES"
    DUPLICATE_SOURCE_SUFFIX = "DUPLICATE_SOURCE_SUFFIX"
    DUPLICATE_SOURCE_ID = "DUPLICATE_SOURCE_ID"
    SOURCE_NOT_OWNED_BY_CAMERA = "SOURCE_NOT_OWNED_BY_CAMERA"
    CAMERA_AGGREGATE_INVALID = "CAMERA_AGGREGATE_INVALID"


@dataclass(frozen=True, slots=True)
class CameraFieldError:
    """一个可直接由后续 HTTP 层转换的领域字段错误。

    ``detail`` 必须是实现定义的固定文本，不能拼接用户输入。这样即使异常被日志系统
    捕获，也不会带出密码或完整 RTSP URL。
    """

    field: str
    code: CameraDomainErrorCode
    detail: str


class CameraDomainError(Exception):
    """所有 Cameras 领域错误的共同基类。"""


class CameraValidationError(CameraDomainError):
    """调用方提供的聚合意图不满足领域约束。"""

    code = "VALIDATION_ERROR"

    def __init__(self, *errors: CameraFieldError) -> None:
        if not errors:
            raise ValueError("CameraValidationError 必须至少包含一个字段错误")
        self.errors = tuple(errors)
        # Exception.args 只保存稳定摘要，避免意外序列化字段值。
        super().__init__(f"Camera 领域校验失败，共 {len(errors)} 项。")


class CameraAggregateCorruptedError(CameraDomainError):
    """持久化数据无法安全重建为 Camera 聚合。"""

    code = "CAMERA_AGGREGATE_INVALID"

    def __init__(self, *issues: CameraFieldError) -> None:
        if not issues:
            raise ValueError("CameraAggregateCorruptedError 必须至少包含一个损坏项")
        self.issues = tuple(issues)
        # 不把 ID、凭据、URL 或底层 Row 放进错误文本。
        super().__init__(f"Camera 聚合数据损坏，共 {len(issues)} 项。")


def validation_error(
    field: str,
    code: CameraDomainErrorCode,
    detail: str,
) -> CameraValidationError:
    """构造单字段校验异常，减少各值规则重复错误包装。"""

    return CameraValidationError(CameraFieldError(field=field, code=code, detail=detail))
