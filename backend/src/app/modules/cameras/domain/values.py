"""Camera 聚合共享的值对象、规范化和基础校验规则。"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from ipaddress import IPv4Address, ip_address
from urllib.parse import quote
from uuid import RFC_4122, UUID

from app.modules.cameras.domain.errors import (
    CameraDomainErrorCode,
    CameraFieldError,
    CameraValidationError,
    validation_error,
)

CAMERA_NAME_MAX_LENGTH = 128
SOURCE_NAME_MAX_LENGTH = 128
USERNAME_MAX_LENGTH = 128
PASSWORD_MAX_LENGTH = 512
URL_SUFFIX_MAX_LENGTH = 1024
RTSP_PORT_MIN = 1
RTSP_PORT_MAX = 65535


@dataclass(frozen=True, slots=True, repr=False)
class SecretValue:
    """默认字符串表示永不回显明文的秘密值。"""

    _value: str = field(repr=False)

    def reveal(self) -> str:
        """只在明确生成详情或 MediaMTX 上游配置时读取明文。"""

        return self._value

    def __repr__(self) -> str:
        return "SecretValue('**********')"

    def __str__(self) -> str:
        return "**********"


@dataclass(frozen=True, slots=True)
class CameraCredentials:
    """Camera 凭据；密码通过 ``SecretValue`` 隔离默认输出。"""

    username: str
    password: SecretValue = field(repr=False)

    def __repr__(self) -> str:
        return f"CameraCredentials(username={self.username!r}, password=**********)"


def _validate_required_string(
    value: str,
    *,
    field_name: str,
    max_length: int,
    trim: bool,
) -> str:
    """执行公共字符串规则；凭据字段通过 ``trim=False`` 保留原始语义。"""

    if not isinstance(value, str):
        raise validation_error(field_name, CameraDomainErrorCode.REQUIRED, "该字段不能为空。")
    normalized = value.strip() if trim else value
    if not normalized:
        raise validation_error(field_name, CameraDomainErrorCode.REQUIRED, "该字段不能为空。")
    if len(normalized) > max_length:
        raise validation_error(
            field_name,
            CameraDomainErrorCode.STRING_TOO_LONG,
            f"该字段不能超过 {max_length} 个字符。",
        )
    return normalized


def normalize_name(value: str, *, field_name: str = "name") -> str:
    """规范化 Camera/Source 名称；名称按照契约去除首尾空白。"""

    return _validate_required_string(
        value,
        field_name=field_name,
        max_length=CAMERA_NAME_MAX_LENGTH,
        trim=True,
    )


def normalize_source_name(value: str, *, field_name: str) -> str:
    """规范化 Source 名称并保留独立长度常量，便于未来契约单独演进。"""

    return _validate_required_string(
        value,
        field_name=field_name,
        max_length=SOURCE_NAME_MAX_LENGTH,
        trim=True,
    )


def normalize_url_suffix(value: str, *, field_name: str = "url_suffix") -> str:
    """按契约 trim 并移除全部前导斜杠，不改动其余字符。"""

    if not isinstance(value, str):
        raise validation_error(
            field_name, CameraDomainErrorCode.REQUIRED, "请输入视频源 URL 后缀。"
        )
    normalized = value.strip().lstrip("/")
    if not normalized:
        raise validation_error(
            field_name, CameraDomainErrorCode.REQUIRED, "请输入视频源 URL 后缀。"
        )
    if len(normalized) > URL_SUFFIX_MAX_LENGTH:
        raise validation_error(
            field_name,
            CameraDomainErrorCode.STRING_TOO_LONG,
            f"视频源 URL 后缀不能超过 {URL_SUFFIX_MAX_LENGTH} 个字符。",
        )
    return normalized


def validate_ipv4(
    value: str | IPv4Address,
    *,
    field_name: str = "ip_address",
) -> IPv4Address:
    """只接受 IPv4；不执行 DNS、连通性或摄像头在线检查。"""

    try:
        parsed = ip_address(value)
    except ValueError:
        raise validation_error(
            field_name,
            CameraDomainErrorCode.INVALID_IP_ADDRESS,
            "请输入合法的 IPv4 地址。",
        ) from None
    if not isinstance(parsed, IPv4Address):
        raise validation_error(
            field_name,
            CameraDomainErrorCode.INVALID_IP_ADDRESS,
            "请输入合法的 IPv4 地址。",
        )
    return parsed


def validate_rtsp_port(value: int, *, field_name: str = "rtsp_port") -> int:
    """验证 RTSP 端口；显式拒绝 Python 中属于 int 子类的 bool。"""

    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not RTSP_PORT_MIN <= value <= RTSP_PORT_MAX
    ):
        raise validation_error(
            field_name,
            CameraDomainErrorCode.OUT_OF_RANGE,
            f"端口必须在 {RTSP_PORT_MIN}-{RTSP_PORT_MAX} 之间。",
        )
    return value


def create_credentials(username: str, password: str) -> CameraCredentials:
    """校验并封装凭据；契约未规定 trim，因此不得静默改变凭据。"""

    normalized_username = _validate_required_string(
        username,
        field_name="username",
        max_length=USERNAME_MAX_LENGTH,
        trim=False,
    )
    normalized_password = _validate_required_string(
        password,
        field_name="password",
        max_length=PASSWORD_MAX_LENGTH,
        trim=False,
    )
    return CameraCredentials(
        username=normalized_username,
        password=SecretValue(normalized_password),
    )


def validate_uuid4(value: UUID, *, field_name: str) -> UUID:
    """验证 UUID 对象确实是 RFC 4122/9562 variant 的 v4。"""

    if not isinstance(value, UUID) or value.version != 4 or value.variant != RFC_4122:
        raise validation_error(
            field_name,
            CameraDomainErrorCode.INVALID_UUID,
            "请输入标准 UUID v4。",
        )
    return value


def normalize_utc_datetime(value: datetime) -> datetime:
    """把带时区时间统一到 UTC；无时区时间属于无法安全解释的损坏数据。"""

    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("领域时间必须包含时区")
    return value.astimezone(UTC)


def build_rtsp_url(
    *,
    credentials: CameraCredentials,
    camera_ip: IPv4Address,
    rtsp_port: int,
    url_suffix: str,
) -> str:
    """按 URI 组件编码生成可直接使用的完整 RTSP URL，不持久化派生结果。

    用户名、密码和 Path 中的保留字符如果直接拼接，可能被客户端误解为凭据分隔符、fragment
    或空白，从而让详情返回的地址无法使用。Source 后缀允许携带 query，因此只保留 ``/``、
    ``?``、``&`` 和 ``=`` 的结构含义，其余字符均按所在组件进行百分号编码。
    """

    path, separator, query = url_suffix.partition("?")
    encoded_suffix = quote(path, safe="/")
    if separator:
        # query 允许多个同名参数，并可能存在没有 ``=`` 的 flag。逐项编码可以保留调用方配置的
        # 参数顺序与结构，又不会让参数值中的 ``:``、``#`` 或空白改变 RTSP URL 的解析结果。
        encoded_pairs: list[str] = []
        for pair in query.split("&"):
            name, value_separator, value = pair.partition("=")
            encoded_name = quote(name, safe="")
            encoded_pairs.append(
                f"{encoded_name}={quote(value, safe='')}" if value_separator else encoded_name
            )
        encoded_suffix = f"{encoded_suffix}?{'&'.join(encoded_pairs)}"

    return (
        f"rtsp://{quote(credentials.username, safe='')}:"
        f"{quote(credentials.password.reveal(), safe='')}@"
        f"{camera_ip}:{rtsp_port}/{encoded_suffix}"
    )


def corrupted_issue(field_name: str, detail: str) -> CameraFieldError:
    """用稳定 code 描述持久化聚合损坏，且不附带原始值。"""

    return CameraFieldError(
        field=field_name,
        code=CameraDomainErrorCode.CAMERA_AGGREGATE_INVALID,
        detail=detail,
    )


def rethrow_as_corruption(error: CameraValidationError) -> tuple[CameraFieldError, ...]:
    """保留稳定字段信息，让重建边界转换为聚合损坏异常。"""

    return error.errors
