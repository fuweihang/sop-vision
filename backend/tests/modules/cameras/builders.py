"""Cameras 领域测试与后续功能切片可复用的确定性 Fixture Builder。"""

from datetime import UTC, datetime
from uuid import UUID

from app.modules.cameras.domain import Camera, CameraSourceChange, NewCameraSource
from app.modules.cameras.domain.testing import FixedClock, FixedIdGenerator

FIXED_TIME = datetime(2026, 8, 24, 8, 0, tzinfo=UTC)


def uuid4_from_index(index: int) -> UUID:
    """生成可读、确定且满足 RFC variant/version 位的测试 UUID v4。"""

    return UUID(f"00000000-0000-4000-8000-{index:012x}")


class CameraSourceBuilder:
    """生成新建或更新 Source 意图，避免各测试复制字段样板。"""

    def __init__(self, index: int = 0) -> None:
        self.index = index
        self.name = f"视频源 {index + 1}"
        self.url_suffix = f"Streaming/Channels/{index + 1:03d}"
        self.is_default_preview = index == 0

    def as_new(self) -> NewCameraSource:
        return NewCameraSource(
            name=self.name,
            url_suffix=self.url_suffix,
            is_default_preview=self.is_default_preview,
        )

    def as_change(self, *, source_id: UUID | None = None) -> CameraSourceChange:
        return CameraSourceChange(
            source_id=source_id,
            name=self.name,
            url_suffix=self.url_suffix,
            is_default_preview=self.is_default_preview,
        )


class CameraBuilder:
    """生成单、双或十 Source 的稳定 Camera 聚合。"""

    def __init__(self) -> None:
        self.name = "洗手区 01"
        self.ip_address = "192.168.1.64"
        self.rtsp_port = 554
        self.username = "admin"
        self.password = "builder-camera-secret"
        self.clock = FixedClock(FIXED_TIME)

    def build(self, *, source_count: int = 2) -> Camera:
        if source_count < 1:
            raise ValueError("CameraBuilder 至少需要一路 Source")
        generated_ids = [uuid4_from_index(index) for index in range(1, source_count + 2)]
        return Camera.create(
            name=self.name,
            ip_address=self.ip_address,
            rtsp_port=self.rtsp_port,
            username=self.username,
            password=self.password,
            sources=tuple(CameraSourceBuilder(index).as_new() for index in range(source_count)),
            id_generator=FixedIdGenerator(generated_ids),
            clock=self.clock,
        )
