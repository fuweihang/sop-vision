"""把 PostgreSQL 拒绝写入的原因换成应用服务能够理解的 Camera 错误。"""

from sqlalchemy.exc import IntegrityError

from app.modules.cameras.application.errors import (
    CameraConstraintViolationError,
    CameraConstraintViolationKind,
    CameraPersistenceError,
    CameraPersistenceOperationError,
)

# 左侧名称来自 Alembic 迁移中声明的数据库约束，右侧是应用服务使用的错误原因。集中维护
# 这张表可以避免 Repository 到处判断字符串，也能保证数据库名称不会继续传到 HTTP 层。
_CONSTRAINT_KINDS = {
    "pk_cameras": CameraConstraintViolationKind.CAMERA_ID_ALREADY_EXISTS,
    "pk_camera_sources": CameraConstraintViolationKind.SOURCE_ID_ALREADY_EXISTS,
    "uq_camera_sources_camera_id_url_suffix": (
        CameraConstraintViolationKind.DUPLICATE_SOURCE_SUFFIX
    ),
    "uq_camera_sources_camera_id_sort_order": (
        CameraConstraintViolationKind.DUPLICATE_SOURCE_ORDER
    ),
    "ck_cameras_ip_address_ipv4": CameraConstraintViolationKind.INVALID_CAMERA_IP,
    "ck_cameras_rtsp_port_range": CameraConstraintViolationKind.INVALID_RTSP_PORT,
    "ck_camera_sources_sort_order_non_negative": (
        CameraConstraintViolationKind.INVALID_SOURCE_ORDER
    ),
}


def translate_integrity_error(error: IntegrityError) -> CameraPersistenceError:
    """把一次数据库完整性错误转换成 Camera 应用错误。

    Psycopg 会在 ``diag.constraint_name`` 中单独提供被违反的数据库约束名称。这里只读取这个
    字段，不读取或解析原始错误消息，因为原始消息可能同时包含 SQL、字段值甚至密码。

    已知名称会转换为具体的 ``CameraConstraintViolationError``；遇到未登记的名称时，返回
    信息更少但安全的 ``CameraPersistenceOperationError``，避免猜错错误原因。
    """

    # 某些测试替身或非 Psycopg 驱动异常可能没有 diag，因此使用 getattr 安全读取。
    diagnostic = getattr(error.orig, "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)
    # DBAPI 异常属于动态边界，第三方驱动或测试替身可能返回 None，甚至返回非字符串值。
    # 只有经过运行时收窄的字符串才允许参与约束映射，避免错误翻译器自身再次抛出异常。
    if not isinstance(constraint_name, str):
        return CameraPersistenceOperationError()
    kind = _CONSTRAINT_KINDS.get(constraint_name)
    if kind is not None:
        return CameraConstraintViolationError(kind)
    return CameraPersistenceOperationError()
