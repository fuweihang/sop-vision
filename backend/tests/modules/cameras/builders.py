"""Cameras 测试使用的确定性时钟、ID 和聚合 Fixture Builder。"""

from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import RFC_4122, UUID

from app.modules.cameras.domain import Camera, CameraSourceChange, NewCameraSource
from tests.modules.cameras.constants import CAMERA_LEAK_SENTINEL

FIXED_TIME = datetime(2026, 8, 24, 8, 0, tzinfo=UTC)


class FixedIdGenerator:
    """按预置顺序返回 UUID v4，耗尽时快速失败而非生成随机值。"""

    def __init__(self, values: Iterable[UUID]) -> None:
        self._values = tuple(values)
        if any(value.version != 4 or value.variant != RFC_4122 for value in self._values):
            raise ValueError("固定 ID 生成器只接受 UUID v4")
        self._index = 0

    def new_id(self) -> UUID:
        if self._index >= len(self._values):
            raise RuntimeError("固定 ID 生成器的预置值已经耗尽")
        value = self._values[self._index]
        self._index += 1
        return value


class FixedClock:
    """返回固定时间，并允许测试显式推进到另一个时刻。"""

    def __init__(self, current: datetime) -> None:
        self.current = current
        self.now_count = 0

    def now(self) -> datetime:
        self.now_count += 1
        return self.current

    def set(self, current: datetime) -> None:
        """显式设置下一次读取值，避免测试依赖真实时间流逝。"""

        self.current = current


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
        self.password = CAMERA_LEAK_SENTINEL
        self.clock = FixedClock(FIXED_TIME)

    def build(self, *, source_count: int = 2, id_start: int = 1) -> Camera:
        """构建聚合；``id_start`` 让列表/事务测试生成互不冲突的确定 ID。"""

        if source_count < 1:
            raise ValueError("CameraBuilder 至少需要一路 Source")
        generated_ids = [
            uuid4_from_index(index) for index in range(id_start, id_start + source_count + 1)
        ]
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


class CameraListBuilder:
    """生成同创建时间、不同稳定 ID 的分页数据，专门验证次排序键不会抖动。"""

    def build(self, count: int, *, source_count: int = 1) -> tuple[Camera, ...]:
        if not 0 <= count <= 100:
            raise ValueError("CameraListBuilder 支持生成 0-100 个 Camera")

        cameras: list[Camera] = []
        for index in range(count):
            builder = CameraBuilder()
            builder.name = f"分页 Camera {index + 1:03d}"
            builder.ip_address = f"192.168.100.{index + 1}"
            cameras.append(
                builder.build(
                    source_count=source_count,
                    # 每个聚合预留 20 个连续 ID，覆盖十 Source Fixture 时仍不会相撞。
                    id_start=1_000 + index * 20,
                )
            )
        return tuple(cameras)
