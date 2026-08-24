"""Camera 数据库操作失败时，应用服务可以识别和处理的错误类型。

这些错误不引用 SQLAlchemy，也不保存 SQL、数据库连接信息、密码或完整 RTSP 地址。后续
HTTP 层只需处理本文件中的错误，无须理解 PostgreSQL 或数据库驱动抛出的原始异常。
"""

from enum import StrEnum


class CameraPersistenceError(Exception):
    """所有 Camera 数据库存取错误的共同父类。

    ``code`` 是供后续错误映射使用的固定标识；它不包含某次请求的数据，因此可以安全地
    记录或转换成 API 错误码。
    """

    code = "CAMERA_PERSISTENCE_ERROR"


class CameraNotFoundError(CameraPersistenceError):
    """保存完整 Camera 配置时，目标 Camera 已不存在。

    普通读取找不到数据会返回 ``None``；只有 ``save`` 明确要求目标必须存在，所以使用异常
    区分“更新失败”和“读取结果为空”。
    """

    code = "CAMERA_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Camera 不存在。")


class CameraConstraintViolationKind(StrEnum):
    """说明数据库具体拒绝了哪一种 Camera 数据。

    PostgreSQL 返回的是迁移中定义的数据库约束名称，例如 ``pk_cameras``。应用服务不应依赖
    这些数据库名称，因此 Repository 会把它们换成本枚举中的含义明确的值。
    """

    # 新建 Camera 时生成了数据库中已经存在的 Camera ID。
    CAMERA_ID_ALREADY_EXISTS = "CAMERA_ID_ALREADY_EXISTS"
    # 新建 Source 时生成了数据库中已经存在的 Source ID。
    SOURCE_ID_ALREADY_EXISTS = "SOURCE_ID_ALREADY_EXISTS"
    # 同一 Camera 中有两路 Source 使用了相同的 URL 后缀。
    DUPLICATE_SOURCE_SUFFIX = "DUPLICATE_SOURCE_SUFFIX"
    # 同一 Camera 中有两路 Source 使用了相同的排序序号。
    DUPLICATE_SOURCE_ORDER = "DUPLICATE_SOURCE_ORDER"
    # 准备写入的 Camera 地址不是合法 IPv4 地址。
    INVALID_CAMERA_IP = "INVALID_CAMERA_IP"
    # 准备写入的 RTSP 端口不在数据库允许的范围内。
    INVALID_RTSP_PORT = "INVALID_RTSP_PORT"
    # 准备写入的 Source 排序序号小于零。
    INVALID_SOURCE_ORDER = "INVALID_SOURCE_ORDER"


class CameraConstraintViolationError(CameraPersistenceError):
    """数据库拒绝了写入，而且拒绝原因已经能用 ``kind`` 准确表示。"""

    code = "CAMERA_CONSTRAINT_VIOLATION"

    def __init__(self, kind: CameraConstraintViolationKind) -> None:
        self.kind = kind
        # 只把上面的固定枚举写入错误消息，避免原始数据库异常带出 SQL、密码或用户输入。
        super().__init__(f"Camera 持久化约束冲突：{kind.value}。")


class CameraPersistenceOperationError(CameraPersistenceError):
    """数据库操作失败，但无法在不泄露内部信息的前提下说明更具体的原因。

    例如连接中断、未知数据库约束或 SQLAlchemy 自身错误都会使用此类型。原始异常仍通过
    Python 异常链保留给服务端诊断，但错误消息本身只包含下面这句通用说明。
    """

    code = "CAMERA_PERSISTENCE_OPERATION_FAILED"

    def __init__(self) -> None:
        super().__init__("Camera 持久化操作失败。")
