"""Cameras 应用层单元测试使用的事务型 Fake Repository 与 UoW。"""

from dataclasses import dataclass, field

from app.modules.cameras.application.errors import (
    CameraConstraintViolationError,
    CameraConstraintViolationKind,
    CameraNotFoundError,
    CameraPersistenceOperationError,
)
from app.modules.cameras.application.ports import (
    CameraListCriteria,
    validate_camera_list_pagination,
)
from app.modules.cameras.domain import Camera, CameraId


@dataclass(slots=True)
class _FakeWorkingState:
    """让 rollback 可替换工作副本，而已创建的 Repository 仍引用同一状态容器。"""

    cameras: dict[CameraId, Camera] = field(default_factory=dict)


class FakeCameraStore:
    """测试显式共享的已提交快照；不提供绕过 Repository 的公共修改接口。"""

    def __init__(self) -> None:
        self._committed: dict[CameraId, Camera] = {}

    def _snapshot(self) -> dict[CameraId, Camera]:
        # Camera 及其 Source 都是 frozen 值，因此浅复制容器即可隔离可变引用。
        return self._committed.copy()

    def _publish(self, cameras: dict[CameraId, Camera]) -> None:
        # 单次引用替换没有 await 点，Fake 在受支持的顺序测试语义下原子发布完整快照。
        self._committed = cameras.copy()


class FakeCameraRepository:
    """与 PostgreSQL 实现共享聚合、搜索、排序和分页契约的内存 Fake。"""

    def __init__(self, state: _FakeWorkingState) -> None:
        self._state = state

    async def add(self, camera: Camera) -> None:
        if camera.camera_id in self._state.cameras:
            raise CameraConstraintViolationError(
                CameraConstraintViolationKind.CAMERA_ID_ALREADY_EXISTS
            )
        existing_source_ids = {
            source.source_id for stored in self._state.cameras.values() for source in stored.sources
        }
        if any(source.source_id in existing_source_ids for source in camera.sources):
            raise CameraConstraintViolationError(
                CameraConstraintViolationKind.SOURCE_ID_ALREADY_EXISTS
            )
        self._state.cameras[camera.camera_id] = camera

    async def save(self, camera: Camera) -> None:
        stored = self._state.cameras.get(camera.camera_id)
        if stored is None:
            raise CameraNotFoundError

        owned_ids = {source.source_id for source in stored.sources}
        foreign_ids = {
            source.source_id
            for camera_id, other in self._state.cameras.items()
            if camera_id != camera.camera_id
            for source in other.sources
        }
        incoming_ids = {source.source_id for source in camera.sources}
        if len(incoming_ids) != len(camera.sources) or any(
            source.camera_id != camera.camera_id for source in camera.sources
        ):
            raise CameraPersistenceOperationError
        if (incoming_ids - owned_ids) & foreign_ids:
            raise CameraPersistenceOperationError
        self._state.cameras[camera.camera_id] = camera

    async def get(self, camera_id: CameraId, for_update: bool = False) -> Camera | None:
        # Fake 明确不模拟 PostgreSQL 行锁；参数只为保持公共 Protocol 一致。
        del for_update
        return self._state.cameras.get(camera_id)

    async def list(
        self,
        criteria: CameraListCriteria,
        page: int,
        page_size: int,
    ) -> tuple[Camera, ...]:
        offset = validate_camera_list_pagination(page, page_size)
        matched = sorted(
            (camera for camera in self._state.cameras.values() if _matches(camera, criteria)),
            key=lambda camera: (camera.created_at, camera.camera_id),
        )
        return tuple(matched[offset : offset + page_size])

    async def count(self, criteria: CameraListCriteria) -> int:
        return sum(_matches(camera, criteria) for camera in self._state.cameras.values())

    async def delete(self, camera_id: CameraId) -> Camera | None:
        return self._state.cameras.pop(camera_id, None)


class FakeCameraUnitOfWork:
    """每例独立工作副本、显式 commit/rollback 的 Camera Unit of Work Fake。"""

    def __init__(self, store: FakeCameraStore) -> None:
        self._store = store
        self._state = _FakeWorkingState(store._snapshot())
        self.cameras = FakeCameraRepository(self._state)

    async def commit(self) -> None:
        self._store._publish(self._state.cameras)

    async def rollback(self) -> None:
        # 回滚后继续使用同一 UoW 时，应看到 Store 最新的已提交状态。
        self._state.cameras = self._store._snapshot()


def _matches(camera: Camera, criteria: CameraListCriteria) -> bool:
    if criteria.q is None:
        return True
    query = criteria.q.casefold()
    return query in camera.name.casefold() or query in str(camera.ip_address).casefold()
