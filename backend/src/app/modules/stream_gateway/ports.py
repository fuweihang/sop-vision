"""业务用例依赖的最小 Stream Gateway Port、错误类别与框架无关数据。"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal, Protocol
from uuid import RFC_4122, UUID


def _validate_uuid4(source_id: UUID) -> None:
    """只允许能够直接作为标准 MediaMTX Path 名称的 UUID v4。"""

    if not isinstance(source_id, UUID) or source_id.version != 4 or source_id.variant != RFC_4122:
        raise ValueError("Source ID 必须是标准 UUID v4。")


def _validate_utc(value: datetime) -> None:
    """拒绝无时区或非 UTC 时间，防止跨批次投影出现不可比较的观察时刻。"""

    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("媒体状态检查时间必须是带时区的 UTC 时间。")


class StreamGatewayUnavailableError(Exception):
    """Control API 超时、网络失败或返回非成功状态。

    异常只携带固定文本，不保留 ``httpx`` Request/Response、请求 URL 或响应正文。这样后续
    Application Service 可以稳定分类故障，同时不会因为默认异常日志泄露上游配置。
    """

    def __init__(self) -> None:
        super().__init__("Stream Gateway 当前不可用。")


class StreamGatewayInvalidResponseError(Exception):
    """Control API 成功响应违反锁定的 JSON、分页或 Path 名称契约。"""

    def __init__(self) -> None:
        super().__init__("Stream Gateway 返回了无效响应。")


class SourceRuntimeStatus(StrEnum):
    """Source 对外只暴露在线/离线二态。"""

    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


class SourceRuntimeErrorCode(StrEnum):
    """状态投影允许进入 Cameras API 的稳定离线原因。"""

    PATH_NOT_FOUND = "MTX_PATH_NOT_FOUND"
    PATH_NOT_AVAILABLE = "MTX_PATH_NOT_AVAILABLE"
    PATH_OFFLINE = "MTX_PATH_OFFLINE"
    CONTROL_API_UNAVAILABLE = "MTX_CONTROL_API_UNAVAILABLE"
    CONTROL_API_INVALID_RESPONSE = "MTX_CONTROL_API_INVALID_RESPONSE"


@dataclass(frozen=True, slots=True)
class DesiredSource:
    """从 PostgreSQL 最新 Camera 配置派生的媒体期望状态。"""

    source_id: UUID
    source_url: str = field(repr=False)
    source_on_demand: Literal[False] = False

    def __post_init__(self) -> None:
        _validate_uuid4(self.source_id)
        if not self.source_url.startswith("rtsp://"):
            raise ValueError("MediaMTX Source URL 必须使用 RTSP。")
        if self.source_on_demand is not False:
            raise ValueError("Cameras MVP 固定 sourceOnDemand=false。")

    @property
    def path_name(self) -> str:
        """UUID 标准文本天然是小写、带连字符的唯一 Path 名称。"""

        return str(self.source_id)


@dataclass(frozen=True, slots=True)
class RuntimePath:
    """状态投影需要的 MediaMTX 运行态字段。"""

    name: str
    available: bool
    online: bool

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("MediaMTX Path 名称不能为空。")
        # bool 是 int 的子类，精确类型检查可拒绝 1 和字符串 "true"。
        if type(self.available) is not bool or type(self.online) is not bool:
            raise TypeError("available 和 online 必须是严格布尔值。")


@dataclass(frozen=True, slots=True)
class RuntimePathSnapshot:
    """完整读取所有分页后形成的不可变运行态快照。"""

    paths: tuple[RuntimePath, ...]
    checked_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.paths, tuple):
            raise TypeError("运行态快照 paths 必须是不可变元组。")
        _validate_utc(self.checked_at)
        if len({path.name for path in self.paths}) != len(self.paths):
            raise ValueError("运行态快照不能包含重复 Path 名称。")


@dataclass(frozen=True, slots=True)
class ConfiguredPath:
    """对账所需的远端配置；带凭据 source 不进入默认表示。"""

    name: str
    source_url: str | None = field(repr=False)
    source_on_demand: bool | None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("MediaMTX Path 名称不能为空。")
        if self.source_url is not None and not isinstance(self.source_url, str):
            raise TypeError("配置 Path source 必须是字符串或未知值。")
        if self.source_on_demand is not None and type(self.source_on_demand) is not bool:
            raise TypeError("配置 Path sourceOnDemand 必须是严格布尔值或未知值。")


@dataclass(frozen=True, slots=True)
class ConfiguredPathSnapshot:
    """完整读取所有分页后形成的不可变配置快照。"""

    paths: tuple[ConfiguredPath, ...]
    checked_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.paths, tuple):
            raise TypeError("配置快照 paths 必须是不可变元组。")
        _validate_utc(self.checked_at)
        if len({path.name for path in self.paths}) != len(self.paths):
            raise ValueError("配置快照不能包含重复 Path 名称。")


@dataclass(frozen=True, slots=True)
class SourceRuntimeProjection:
    """一次完整 Control API 观察得到的单 Source 不可变媒体投影。"""

    source_id: UUID
    status: SourceRuntimeStatus
    last_checked_at: datetime
    error: SourceRuntimeErrorCode | None
    whep_url: str | None

    def __post_init__(self) -> None:
        _validate_uuid4(self.source_id)
        _validate_utc(self.last_checked_at)
        if not isinstance(self.status, SourceRuntimeStatus):
            raise TypeError("Source 运行状态必须使用稳定枚举。")
        if self.error is not None and not isinstance(self.error, SourceRuntimeErrorCode):
            raise TypeError("Source 运行错误必须使用稳定枚举或 null。")

        # 在线与离线字段组合是公共响应的关键不变量。集中拒绝非法组合，避免后续多个
        # Application Service 各自拼装出互相矛盾的状态、错误和播放地址。
        if self.status is SourceRuntimeStatus.ONLINE:
            if self.error is not None or not self.whep_url or not self.whep_url.strip():
                raise ValueError("ONLINE Source 必须仅包含非空 WHEP URL。")
        elif self.error is None or self.whep_url is not None:
            raise ValueError("OFFLINE Source 必须包含错误且 WHEP URL 为 null。")


class StreamGatewayPort(Protocol):
    """应用层唯一可见的媒体能力；具体 HTTP Adapter 属于 03。"""

    async def fetch_runtime_path_snapshot(self) -> RuntimePathSnapshot: ...

    async def fetch_config_path_snapshot(self) -> ConfiguredPathSnapshot: ...

    async def ensure_path(self, desired_source: DesiredSource) -> None: ...

    async def release_path(self, source_id: UUID) -> None: ...

    def whep_url_for(self, source_id: UUID) -> str: ...
