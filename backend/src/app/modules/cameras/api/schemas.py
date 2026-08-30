"""Cameras 公共 HTTP 请求与响应 Schema。

本模块是 Camera 配置 API 的唯一 Pydantic Schema 来源。它只描述传输契约，并复用 Application
定义的框架无关状态枚举；不依赖 ORM、Repository 或业务用例实现。
"""

from ipaddress import IPv4Address
from typing import Annotated, Any

from pydantic import (
    UUID4,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
)
from pydantic_core import PydanticCustomError

from app.core.http import CanonicalUUID4
from app.modules.cameras.application import CameraStatus
from app.modules.stream_gateway.ports import SourceRuntimeErrorCode, SourceRuntimeStatus

# 契约 example 只使用 RFC 5737 文档网段、example.invalid 域名和明确的测试凭据。固定 ID 与
# 时间让连续生成 OpenAPI 时字节稳定，也避免开发者误把真实 Camera 数据复制进生成物。
CAMERA_ID_EXAMPLE = "6f9619ff-8b86-4e4f-9f68-bb3f8f6f4f21"
PRIMARY_SOURCE_ID_EXAMPLE = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
SECONDARY_SOURCE_ID_EXAMPLE = "8f14e45f-ea9d-4a7d-9b6d-8c9f0a1b2c3d"
CREATED_AT_EXAMPLE = "2026-08-19T03:00:00Z"
UPDATED_AT_EXAMPLE = "2026-08-19T03:10:00Z"
LAST_CHECKED_AT_EXAMPLE = "2026-08-19T03:10:01Z"
TEST_USERNAME = "openapi-test-user"
# 该值是敏感数据门禁唯一的泄漏 canary。它会合法出现在写请求和 CameraDetail example 中；
# 列表、Problem 与日志的专项测试则必须证明该值无法越过各自的安全边界。
TEST_PASSWORD = "cameras-mvp-leak-sentinel"


def _normalize_url_suffix(value: Any) -> Any:
    """按领域冻结规则规范化 Source 后缀，再交给字符串长度约束。

    非字符串原样交回 Pydantic，使框架产生标准类型错误；这里不调用 ``str(value)``，否则
    数字或对象会被意外接纳。去掉全部前导斜杠后再检查非空，保证 ``///`` 不会绕过必填规则。
    """

    if not isinstance(value, str):
        return value
    return value.strip().lstrip("/")


CameraName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]
SourceName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]
Username = Annotated[str, StringConstraints(min_length=1, max_length=128)]
Password = Annotated[str, StringConstraints(min_length=1, max_length=512)]
UrlSuffix = Annotated[
    str,
    BeforeValidator(_normalize_url_suffix),
    StringConstraints(min_length=1, max_length=1024),
]


class _RequestModel(BaseModel):
    """全部 Cameras 请求共享的防 mass-assignment 配置。"""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class _ResponseModel(BaseModel):
    """冻结响应对象，防止投影完成后被路由层临时追加敏感字段。"""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class CameraSourceCreateRequest(_RequestModel):
    """创建 Camera 时的一路 Source；ID 只能由服务端生成。"""

    name: SourceName
    url_suffix: UrlSuffix
    is_default_preview: bool


def _require_create_sources(value: Any) -> Any:
    """为空数组生成创建业务专用错误，同时把其他输入交给 Pydantic 正常校验。

    自定义错误不附加 ``ctx`` 或原始值；公共转换器只读取错误类型和位置。字段仍保留
    ``min_length=1``，因此 OpenAPI 会继续声明 ``minItems=1``。
    """

    if isinstance(value, (list, tuple)) and not value:
        raise PydanticCustomError(
            "camera_source_required",
            "创建 Camera 至少需要一路 Source。",
        )
    return value


CameraCreateSources = Annotated[
    list[CameraSourceCreateRequest],
    BeforeValidator(_require_create_sources),
]


class CameraCreateRequest(_RequestModel):
    """创建完整 Camera 聚合的请求。"""

    model_config = ConfigDict(
        extra="forbid",
        hide_input_in_errors=True,
        json_schema_extra={
            "examples": [
                {
                    "name": "洗手区 01",
                    "ip_address": "192.0.2.64",
                    "rtsp_port": 554,
                    "username": TEST_USERNAME,
                    "password": TEST_PASSWORD,
                    "sources": [
                        {
                            "name": "主码流",
                            "url_suffix": "Streaming/Channels/101",
                            "is_default_preview": True,
                        },
                        {
                            "name": "子码流",
                            "url_suffix": "/Streaming/Channels/102",
                            "is_default_preview": False,
                        },
                    ],
                }
            ]
        },
    )

    name: CameraName
    ip_address: IPv4Address
    rtsp_port: int = Field(default=554, ge=1, le=65535)
    username: Username
    password: Password
    sources: CameraCreateSources = Field(min_length=1)


class CameraSourceUpdateRequest(_RequestModel):
    """PUT 中的一路 Source；无 ID 表示新增，有 ID 表示保留并完整更新。"""

    source_id: CanonicalUUID4 | None = None
    name: SourceName
    url_suffix: UrlSuffix
    is_default_preview: bool


class CameraUpdateRequest(_RequestModel):
    """完整替换 Camera 可变配置与 Source 集合的请求。"""

    model_config = ConfigDict(
        extra="forbid",
        hide_input_in_errors=True,
        json_schema_extra={
            "examples": [
                {
                    "name": "洗手区东侧 01",
                    "ip_address": "192.0.2.65",
                    "rtsp_port": 554,
                    "username": TEST_USERNAME,
                    "password": TEST_PASSWORD,
                    "sources": [
                        {
                            "source_id": PRIMARY_SOURCE_ID_EXAMPLE,
                            "name": "子码流",
                            "url_suffix": "Streaming/Channels/102",
                            "is_default_preview": True,
                        },
                        {
                            "name": "通道 2",
                            "url_suffix": "Streaming/Channels/201",
                            "is_default_preview": False,
                        },
                    ],
                }
            ]
        },
    )

    name: CameraName
    ip_address: IPv4Address
    # PUT 是完整替换；创建时的 554 默认值不能让调用方遗漏现有端口并静默重置配置。
    rtsp_port: int = Field(ge=1, le=65535)
    username: Username
    password: Password
    sources: list[CameraSourceUpdateRequest] = Field(min_length=1)


class SetDefaultPreviewSourceRequest(_RequestModel):
    """把一个属于当前 Camera 的 Source 设为默认预览源。"""

    model_config = ConfigDict(
        extra="forbid",
        hide_input_in_errors=True,
        json_schema_extra={"examples": [{"source_id": PRIMARY_SOURCE_ID_EXAMPLE}]},
    )

    source_id: CanonicalUUID4


class CameraSourceDetail(_ResponseModel):
    """CameraDetail 内唯一允许包含连接后缀和完整 RTSP URL 的 Source 形状。"""

    source_id: UUID4
    name: str
    url_suffix: str
    rtsp_url: str
    is_default_preview: bool
    status: SourceRuntimeStatus
    last_checked_at: AwareDatetime
    error: SourceRuntimeErrorCode | None
    whep_url: str | None


class CameraDetail(_ResponseModel):
    """创建、详情和更新共用的敏感完整响应，调用方必须遵守 ``no-store``。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        json_schema_extra={
            "examples": [
                {
                    "camera_id": CAMERA_ID_EXAMPLE,
                    "name": "洗手区 01",
                    "ip_address": "192.0.2.64",
                    "rtsp_port": 554,
                    # 这是专用于生成契约的测试凭据；example.invalid 与文档网段不可路由。
                    "username": TEST_USERNAME,
                    "password": TEST_PASSWORD,
                    "default_preview_source_id": PRIMARY_SOURCE_ID_EXAMPLE,
                    "status": "DEGRADED",
                    "online_source_count": 1,
                    "source_count": 2,
                    "sources": [
                        {
                            "source_id": PRIMARY_SOURCE_ID_EXAMPLE,
                            "name": "主码流",
                            "url_suffix": "Streaming/Channels/101",
                            "rtsp_url": (
                                f"rtsp://{TEST_USERNAME}:{TEST_PASSWORD}@"
                                "192.0.2.64:554/Streaming/Channels/101"
                            ),
                            "is_default_preview": True,
                            "status": "ONLINE",
                            "last_checked_at": LAST_CHECKED_AT_EXAMPLE,
                            "error": None,
                            "whep_url": (
                                f"https://media.example.invalid/{PRIMARY_SOURCE_ID_EXAMPLE}/whep"
                            ),
                        },
                        {
                            "source_id": SECONDARY_SOURCE_ID_EXAMPLE,
                            "name": "子码流",
                            "url_suffix": "Streaming/Channels/102",
                            "rtsp_url": (
                                f"rtsp://{TEST_USERNAME}:{TEST_PASSWORD}@"
                                "192.0.2.64:554/Streaming/Channels/102"
                            ),
                            "is_default_preview": False,
                            "status": "OFFLINE",
                            "last_checked_at": LAST_CHECKED_AT_EXAMPLE,
                            "error": "MTX_PATH_NOT_FOUND",
                            "whep_url": None,
                        },
                    ],
                    "created_at": CREATED_AT_EXAMPLE,
                    "updated_at": UPDATED_AT_EXAMPLE,
                }
            ]
        },
    )

    camera_id: UUID4
    name: str
    ip_address: IPv4Address
    rtsp_port: int = Field(ge=1, le=65535)
    username: str
    password: str
    default_preview_source_id: UUID4
    status: CameraStatus
    online_source_count: int = Field(ge=0)
    source_count: int = Field(ge=1)
    sources: list[CameraSourceDetail] = Field(min_length=1)
    created_at: AwareDatetime
    updated_at: AwareDatetime


class DefaultPreviewSourceSummary(_ResponseModel):
    """列表卡片所需的默认源非敏感投影。"""

    source_id: UUID4
    name: str
    status: SourceRuntimeStatus
    last_checked_at: AwareDatetime
    whep_url: str | None


class CameraSummary(_ResponseModel):
    """列表项的非敏感 Camera 摘要。"""

    camera_id: UUID4
    name: str
    ip_address: IPv4Address
    rtsp_port: int = Field(ge=1, le=65535)
    status: CameraStatus
    online_source_count: int = Field(ge=0)
    source_count: int = Field(ge=1)
    default_preview_source: DefaultPreviewSourceSummary
    created_at: AwareDatetime
    updated_at: AwareDatetime


class CameraPage(_ResponseModel):
    """稳定分页的 Camera 列表响应。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        json_schema_extra={
            "examples": [
                {
                    "items": [
                        {
                            "camera_id": CAMERA_ID_EXAMPLE,
                            "name": "洗手区 01",
                            "ip_address": "192.0.2.64",
                            "rtsp_port": 554,
                            "status": "ONLINE",
                            "online_source_count": 2,
                            "source_count": 2,
                            "default_preview_source": {
                                "source_id": PRIMARY_SOURCE_ID_EXAMPLE,
                                "name": "主码流",
                                "status": "ONLINE",
                                "last_checked_at": LAST_CHECKED_AT_EXAMPLE,
                                "whep_url": (
                                    "https://media.example.invalid/"
                                    f"{PRIMARY_SOURCE_ID_EXAMPLE}/whep"
                                ),
                            },
                            "created_at": CREATED_AT_EXAMPLE,
                            "updated_at": UPDATED_AT_EXAMPLE,
                        }
                    ],
                    "page": 1,
                    "page_size": 20,
                    "total": 1,
                }
            ]
        },
    )

    items: list[CameraSummary]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


class DefaultPreviewSourceResponse(_ResponseModel):
    """默认源切换成功后的最小确认响应。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        json_schema_extra={
            "examples": [
                {
                    "camera_id": CAMERA_ID_EXAMPLE,
                    "default_preview_source_id": PRIMARY_SOURCE_ID_EXAMPLE,
                    "updated_at": UPDATED_AT_EXAMPLE,
                }
            ]
        },
    )

    camera_id: UUID4
    default_preview_source_id: UUID4
    updated_at: AwareDatetime
