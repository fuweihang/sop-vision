"""Cameras 应用测试使用的事务型 Fake Repository、UoW 与媒体端口。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from uuid import UUID

from app.modules.cameras.application.errors import (
    CameraConstraintViolationError,
    CameraConstraintViolationKind,
    CameraNotFoundError,
    CameraPersistenceOperationError,
)
from app.modules.cameras.application.ports import (
    CameraListCriteria,
    CameraMediaStateReader,
    validate_camera_list_pagination,
)
from app.modules.cameras.domain import Camera, CameraId
from app.modules.stream_gateway.ports import (
    ConfiguredPath,
    ConfiguredPathSnapshot,
    DesiredSource,
    RuntimePathSnapshot,
)


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

    def __init__(self, state: _FakeWorkingState, operation_log: list[str]) -> None:
        self._state = state
        self._operation_log = operation_log
        # 详情用例需要覆盖数据库失败、聚合损坏和任务取消，同时保持 Fake 的 get 签名与真实
        # Repository 一致。测试只设置脱敏应用/领域异常，不在这里模拟 SQLAlchemy 异常细节。
        self.get_error: BaseException | None = None
        # 更新用例需要模拟锁定读取成功但完整保存失败，不能用 get_error 代替这一阶段。
        self.save_error: BaseException | None = None
        # 列表会先 count 再 list；两个独立注入点可以证明任一数据库阶段失败后都不会访问媒体服务。
        self.count_error: BaseException | None = None
        self.list_error: BaseException | None = None

    async def add(self, camera: Camera) -> None:
        self._operation_log.append(f"repository.add:{camera.camera_id}")
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
        self._operation_log.append(f"repository.save:{camera.camera_id}")
        if self.save_error is not None:
            raise self.save_error
        stored = self._state.cameras.get(camera.camera_id)
        if stored is None:
            raise CameraNotFoundError(camera.camera_id)

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
        # Fake 不模拟 PostgreSQL 行锁，但会保留调用参数，详情测试可以证明普通读取没有误加锁。
        self._operation_log.append(f"repository.get:{camera_id}:{for_update}")
        if self.get_error is not None:
            raise self.get_error
        return self._state.cameras.get(camera_id)

    async def list(
        self,
        criteria: CameraListCriteria,
        page: int,
        page_size: int,
    ) -> tuple[Camera, ...]:
        self._operation_log.append(f"repository.list:{criteria.q}:{page}:{page_size}")
        if self.list_error is not None:
            raise self.list_error
        offset = validate_camera_list_pagination(page, page_size)
        matched = sorted(
            (camera for camera in self._state.cameras.values() if _matches(camera, criteria)),
            key=lambda camera: (camera.created_at, camera.camera_id),
        )
        return tuple(matched[offset : offset + page_size])

    async def count(self, criteria: CameraListCriteria) -> int:
        self._operation_log.append(f"repository.count:{criteria.q}")
        if self.count_error is not None:
            raise self.count_error
        return sum(_matches(camera, criteria) for camera in self._state.cameras.values())

    async def delete(self, camera_id: CameraId) -> Camera | None:
        return self._state.cameras.pop(camera_id, None)


class FakeCameraUnitOfWork:
    """每例独立工作副本、显式 commit/rollback 的 Camera Unit of Work Fake。"""

    def __init__(
        self,
        store: FakeCameraStore,
        *,
        operation_log: list[str] | None = None,
    ) -> None:
        self._store = store
        self._state = _FakeWorkingState(store._snapshot())
        # 查询测试可让 UoW 与 Stream Gateway 共用一个列表，以验证外部 I/O 发生在事务结束后。
        # 其他测试不传时仍得到每例独立列表，不改变原有 Fake 行为。
        self.operation_log = operation_log if operation_log is not None else []
        self.cameras = FakeCameraRepository(self._state, self.operation_log)
        self.commit_count = 0
        self.rollback_count = 0
        # 写流程需要分别验证普通提交失败和任务取消。统一注入点可避免每个测试文件都创建
        # 行为相同的 UoW 子类；异常发生在发布快照前，因此已提交 Store 仍保持旧事实。
        self.commit_error: BaseException | None = None

    async def commit(self) -> None:
        self.operation_log.append("uow.commit")
        self.commit_count += 1
        if self.commit_error is not None:
            raise self.commit_error
        self._store._publish(self._state.cameras)

    async def rollback(self) -> None:
        self.operation_log.append("uow.rollback")
        self.rollback_count += 1
        # 回滚后继续使用同一 UoW 时，应看到 Store 最新的已提交状态。
        self._state.cameras = self._store._snapshot()


class FakeStreamGateway:
    """Camera 应用测试使用的可控媒体 Port，不模拟 HTTP 协议细节。"""

    def __init__(
        self,
        runtime_observation: RuntimePathSnapshot | BaseException,
        *,
        whep_base_url: str = "https://media.example.invalid",
        operation_log: list[str] | None = None,
    ) -> None:
        self.runtime_observation = runtime_observation
        self.whep_base_url = whep_base_url.rstrip("/")
        self.ensure_failures: dict[UUID, BaseException] = {}
        self.release_failures: dict[UUID, BaseException] = {}
        self.ensure_calls: list[DesiredSource] = []
        self.release_calls: list[UUID] = []
        self.runtime_snapshot_count = 0
        self.whep_source_ids: list[UUID] = []
        self.operation_log = operation_log

    async def fetch_runtime_path_snapshot(self) -> RuntimePathSnapshot:
        if self.operation_log is not None:
            self.operation_log.append("stream_gateway.fetch_runtime_path_snapshot")
        self.runtime_snapshot_count += 1
        if isinstance(self.runtime_observation, BaseException):
            raise self.runtime_observation
        return self.runtime_observation

    async def ensure_path(self, desired_source: DesiredSource) -> None:
        if self.operation_log is not None:
            self.operation_log.append(f"stream_gateway.ensure_path:{desired_source.source_id}")
        self.ensure_calls.append(desired_source)
        failure = self.ensure_failures.get(desired_source.source_id)
        if failure is not None:
            raise failure

    def whep_url_for(self, source_id: UUID) -> str:
        self.whep_source_ids.append(source_id)
        return f"{self.whep_base_url}/{source_id}/whep"

    async def fetch_config_path_snapshot(self) -> ConfiguredPathSnapshot:
        raise AssertionError("Camera 创建用例不应读取 MediaMTX 配置快照。")

    async def release_path(self, source_id: UUID) -> None:
        if self.operation_log is not None:
            self.operation_log.append(f"stream_gateway.release_path:{source_id}")
        self.release_calls.append(source_id)
        failure = self.release_failures.get(source_id)
        if failure is not None:
            raise failure


class FakeMediaStateReader:
    """提供可变的全量 Camera 快照，并允许测试注入数据库/Mapper 失败。"""

    def __init__(
        self,
        cameras: tuple[Camera, ...] = (),
        *,
        error: BaseException | None = None,
    ) -> None:
        self.cameras = cameras
        self.error = error
        self.read_count = 0

    async def read_all(self) -> tuple[Camera, ...]:
        self.read_count += 1
        if self.error is not None:
            raise self.error
        return self.cameras


class FakeMediaReconciliationLease:
    """返回固定 Reader 或锁竞争结果，并记录取消/异常路径是否释放 Lease。"""

    def __init__(self, reader: CameraMediaStateReader | None) -> None:
        self.reader = reader
        self.enter_count = 0
        self.exit_count = 0

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[CameraMediaStateReader | None]:
        self.enter_count += 1
        try:
            yield self.reader
        finally:
            # 对账取消时也必须走到这里，否则真实实现会遗留 advisory lock 和连接。
            self.exit_count += 1


class FakeReconciliationStreamGateway:
    """维护可变配置快照，供多轮对账测试观察最终远端状态和写入顺序。"""

    def __init__(self, configured_snapshot: ConfiguredPathSnapshot) -> None:
        self._checked_at = configured_snapshot.checked_at
        self.configured_paths = {path.name: path for path in configured_snapshot.paths}
        self.snapshot_error: BaseException | None = None
        self.fetch_count = 0
        self.operations: list[tuple[str, UUID]] = []
        self.ensure_failures: dict[UUID, BaseException] = {}
        self.release_failures: dict[UUID, BaseException] = {}

    async def fetch_config_path_snapshot(self) -> ConfiguredPathSnapshot:
        self.fetch_count += 1
        if self.snapshot_error is not None:
            raise self.snapshot_error
        return ConfiguredPathSnapshot(
            paths=tuple(self.configured_paths.values()),
            checked_at=self._checked_at,
        )

    async def ensure_path(self, desired_source: DesiredSource) -> None:
        self.operations.append(("ensure", desired_source.source_id))
        failure = self.ensure_failures.get(desired_source.source_id)
        if failure is not None:
            raise failure
        self.configured_paths[desired_source.path_name] = ConfiguredPath(
            name=desired_source.path_name,
            source_url=desired_source.source_url,
            source_on_demand=False,
        )

    async def release_path(self, source_id: UUID) -> None:
        self.operations.append(("release", source_id))
        failure = self.release_failures.get(source_id)
        if failure is not None:
            raise failure
        self.configured_paths.pop(str(source_id), None)

    async def fetch_runtime_path_snapshot(self) -> RuntimePathSnapshot:
        raise AssertionError("媒体对账不应读取运行态 Path。")

    def whep_url_for(self, source_id: UUID) -> str:
        raise AssertionError(f"媒体对账不应构造 WHEP URL：{source_id}")


def _matches(camera: Camera, criteria: CameraListCriteria) -> bool:
    if criteria.q is None:
        return True
    query = criteria.q.casefold()
    return query in camera.name.casefold() or query in str(camera.ip_address).casefold()
