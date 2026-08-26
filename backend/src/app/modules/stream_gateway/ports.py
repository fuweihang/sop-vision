"""业务用例依赖的最小 Stream Gateway Port 与框架无关数据。"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol
from uuid import RFC_4122, UUID


def _validate_uuid4(source_id: UUID) -> None:
    """只允许能够直接作为标准 MediaMTX Path 名称的 UUID v4。"""

    if source_id.version != 4 or source_id.variant != RFC_4122:
        raise ValueError("Source ID 必须是标准 UUID v4。")


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
        # bool 是 int 的子类，精确类型检查可拒绝 1 和字符串 "true"。
        if type(self.available) is not bool or type(self.online) is not bool:
            raise TypeError("available 和 online 必须是严格布尔值。")


@dataclass(frozen=True, slots=True)
class RuntimePathSnapshot:
    """完整读取所有分页后形成的不可变运行态快照。"""

    paths: tuple[RuntimePath, ...]
    checked_at: datetime


@dataclass(frozen=True, slots=True)
class ConfiguredPath:
    """对账所需的远端配置；带凭据 source 不进入默认表示。"""

    name: str
    source_url: str | None = field(repr=False)
    source_on_demand: bool | None


@dataclass(frozen=True, slots=True)
class ConfiguredPathSnapshot:
    """完整读取所有分页后形成的不可变配置快照。"""

    paths: tuple[ConfiguredPath, ...]
    checked_at: datetime


class StreamGatewayPort(Protocol):
    """应用层唯一可见的媒体能力；具体 HTTP Adapter 属于 03。"""

    async def fetch_runtime_path_snapshot(self) -> RuntimePathSnapshot: ...

    async def fetch_config_path_snapshot(self) -> ConfiguredPathSnapshot: ...

    async def ensure_path(self, desired_source: DesiredSource) -> None: ...

    async def release_path(self, source_id: UUID) -> None: ...

    def whep_url_for(self, source_id: UUID) -> str: ...
