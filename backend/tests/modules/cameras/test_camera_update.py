"""Camera 完整更新 Application 的事务、媒体差异与安全边界测试。"""

import asyncio
import logging
from datetime import UTC, datetime

import pytest

from app.modules.cameras.application import (
    CameraAggregateInvalidError,
    CameraNotFoundError,
    CameraPersistenceOperationError,
    CameraStatus,
    UpdateCameraCommand,
    UpdateCameraSourceCommand,
    update_camera,
)
from app.modules.cameras.domain import (
    Camera,
    CameraAggregateCorruptedError,
    CameraDomainErrorCode,
    CameraFieldError,
    CameraValidationError,
)
from app.modules.stream_gateway.ports import (
    RuntimePath,
    RuntimePathSnapshot,
    SourceRuntimeErrorCode,
    StreamGatewayInvalidResponseError,
    StreamGatewayUnavailableError,
)
from tests.modules.cameras.builders import (
    CameraBuilder,
    FixedClock,
    FixedIdGenerator,
    uuid4_from_index,
)
from tests.modules.cameras.constants import CAMERA_LEAK_SENTINEL
from tests.modules.cameras.fakes import (
    FakeCameraStore,
    FakeCameraUnitOfWork,
    FakeStreamGateway,
)

pytestmark = pytest.mark.anyio

UPDATED_AT = datetime(2026, 9, 2, 8, 0, tzinfo=UTC)
SNAPSHOT_AT = datetime(2026, 9, 2, 8, 0, 1, tzinfo=UTC)
FAILED_AT = datetime(2026, 9, 2, 8, 0, 2, tzinfo=UTC)
NEW_SOURCE_ID = uuid4_from_index(900)


async def store_camera(camera: Camera) -> FakeCameraStore:
    """通过 Fake Repository/UoW 写入初始聚合，保留真实事务使用方式。"""

    store = FakeCameraStore()
    writer = FakeCameraUnitOfWork(store)
    await writer.cameras.add(camera)
    await writer.commit()
    return store


def replacement_command(camera: Camera) -> UpdateCameraCommand:
    """保留第二路、增加一路并删除其余 Source，供编排测试复用。"""

    second = camera.sources[1]
    return UpdateCameraCommand(
        camera_id=camera.camera_id,
        name=" 更新后的 Camera ",
        ip_address=camera.ip_address,
        rtsp_port=camera.rtsp_port,
        username=camera.credentials.username,
        password=camera.credentials.password.reveal(),
        sources=(
            UpdateCameraSourceCommand(
                source_id=second.source_id,
                name=" 保留并修改后缀 ",
                url_suffix=" /changed/stream/2 ",
                is_default_preview=True,
            ),
            UpdateCameraSourceCommand(
                name=" 新增 Source ",
                url_suffix=" /new/stream ",
                is_default_preview=False,
            ),
        ),
    )


async def test_update_camera_commits_before_ordered_media_diff_and_returns_one_snapshot() -> None:
    """增删改排在一次提交完成，媒体严格 ensure-before-release 并只读取一次快照。"""

    camera = CameraBuilder().build(source_count=3)
    first, second, third = camera.sources
    operation_log: list[str] = []
    store = await store_camera(camera)
    uow = FakeCameraUnitOfWork(store, operation_log=operation_log)
    gateway = FakeStreamGateway(
        RuntimePathSnapshot(
            paths=(
                RuntimePath(name=str(second.source_id), available=True, online=True),
                RuntimePath(name=str(NEW_SOURCE_ID), available=True, online=True),
            ),
            checked_at=SNAPSHOT_AT,
        ),
        operation_log=operation_log,
    )

    result = await update_camera(
        replacement_command(camera),
        uow=uow,
        stream_gateway=gateway,
        id_generator=FixedIdGenerator((NEW_SOURCE_ID,)),
        clock=FixedClock(UPDATED_AT),
    )

    assert result.camera.name == "更新后的 Camera"
    assert tuple(source.source_id for source in result.camera.sources) == (
        second.source_id,
        NEW_SOURCE_ID,
    )
    assert tuple(source.sort_order for source in result.camera.sources) == (0, 1)
    assert result.camera.sources[0].created_at == second.created_at
    assert result.camera.sources[0].updated_at == UPDATED_AT
    assert result.camera.sources[1].created_at == UPDATED_AT
    assert result.camera.default_preview_source_id == second.source_id
    assert result.runtime_summary.status is CameraStatus.ONLINE
    assert result.runtime_summary.online_source_count == 2
    assert gateway.runtime_snapshot_count == 1
    assert tuple(item.source_id for item in gateway.ensure_calls) == (
        second.source_id,
        NEW_SOURCE_ID,
    )
    assert gateway.release_calls == [first.source_id, third.source_id]
    assert operation_log == [
        f"repository.get:{camera.camera_id}:True",
        f"repository.save:{camera.camera_id}",
        "uow.commit",
        f"stream_gateway.ensure_path:{second.source_id}",
        f"stream_gateway.ensure_path:{NEW_SOURCE_ID}",
        f"stream_gateway.release_path:{first.source_id}",
        f"stream_gateway.release_path:{third.source_id}",
        "stream_gateway.fetch_runtime_path_snapshot",
    ]

    reader = FakeCameraUnitOfWork(store)
    assert await reader.cameras.get(camera.camera_id) == result.camera


async def test_update_camera_continues_supported_media_failures_and_degrades_snapshot(
    caplog,
) -> None:
    """受支持的 ensure/release/快照故障全部计数，且不阻塞后续媒体操作。"""

    camera = CameraBuilder().build(source_count=3)
    first, second, third = camera.sources
    store = await store_camera(camera)
    gateway = FakeStreamGateway(StreamGatewayUnavailableError())
    gateway.ensure_failures[second.source_id] = StreamGatewayInvalidResponseError()
    gateway.release_failures[first.source_id] = StreamGatewayUnavailableError()
    clock = FixedClock(UPDATED_AT)

    # 领域更新读取 UPDATED_AT；媒体快照失败前推进时钟，证明投影只读取一次失败完成时间。
    original_fetch = gateway.fetch_runtime_path_snapshot

    async def fetch_after_clock_advance() -> RuntimePathSnapshot:
        clock.set(FAILED_AT)
        return await original_fetch()

    gateway.fetch_runtime_path_snapshot = fetch_after_clock_advance  # type: ignore[method-assign]
    with caplog.at_level(logging.WARNING, logger="app.modules.cameras.application.update"):
        result = await update_camera(
            replacement_command(camera),
            uow=FakeCameraUnitOfWork(store),
            stream_gateway=gateway,
            id_generator=FixedIdGenerator((NEW_SOURCE_ID,)),
            clock=clock,
        )

    assert tuple(item.source_id for item in gateway.ensure_calls) == (
        second.source_id,
        NEW_SOURCE_ID,
    )
    assert gateway.release_calls == [first.source_id, third.source_id]
    assert result.runtime_summary.status is CameraStatus.OFFLINE
    assert all(
        item.error is SourceRuntimeErrorCode.CONTROL_API_UNAVAILABLE
        for item in result.source_runtime
    )
    assert all(item.last_checked_at == FAILED_AT for item in result.source_runtime)
    record = next(
        item for item in caplog.records if item.name == "app.modules.cameras.application.update"
    )
    assert record.event == "camera.update_media_sync_degraded"
    assert record.failed_count == 3
    assert CAMERA_LEAK_SENTINEL not in caplog.text


async def test_update_camera_rolls_back_domain_error_before_media() -> None:
    """锁定读取后的领域校验失败必须释放事务，且不保存或访问媒体。"""

    camera = CameraBuilder().build(source_count=2)
    uow = FakeCameraUnitOfWork(await store_camera(camera))
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))
    command = UpdateCameraCommand(
        camera_id=camera.camera_id,
        name=camera.name,
        ip_address=camera.ip_address,
        rtsp_port=camera.rtsp_port,
        username=camera.credentials.username,
        password=CAMERA_LEAK_SENTINEL,
        sources=(),
    )

    with pytest.raises(CameraValidationError) as captured:
        await update_camera(
            command,
            uow=uow,
            stream_gateway=gateway,
            id_generator=FixedIdGenerator(()),
            clock=FixedClock(UPDATED_AT),
        )

    assert [(item.field, item.code.value) for item in captured.value.errors] == [
        ("sources", "SOURCE_REQUIRED")
    ]
    assert uow.rollback_count == 1
    assert uow.commit_count == 0
    assert gateway.ensure_calls == []
    assert gateway.release_calls == []
    assert gateway.runtime_snapshot_count == 0


async def test_update_camera_does_not_mislabel_server_clock_error_as_persisted_corruption() -> None:
    """领域阶段的服务端不变量错误沿用内部 500，不转换成持久化聚合损坏。"""

    camera = CameraBuilder().build(source_count=3)
    uow = FakeCameraUnitOfWork(await store_camera(camera))
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))

    with pytest.raises(CameraAggregateCorruptedError):
        await update_camera(
            replacement_command(camera),
            uow=uow,
            stream_gateway=gateway,
            id_generator=FixedIdGenerator((NEW_SOURCE_ID,)),
            # 明确早于当前聚合时间，模拟注入 Clock 违反服务端单调时间要求。
            clock=FixedClock(datetime(2020, 1, 1, tzinfo=UTC)),
        )

    assert uow.rollback_count == 1
    assert uow.commit_count == 0
    assert gateway.ensure_calls == []
    assert gateway.release_calls == []
    assert gateway.runtime_snapshot_count == 0


async def test_update_camera_missing_and_corrupted_aggregate_ends_transaction_without_media() -> (
    None
):
    """不存在与损坏聚合分别转换 404/500，并都在媒体边界前停止。"""

    missing_id = uuid4_from_index(777)
    missing_uow = FakeCameraUnitOfWork(FakeCameraStore())
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))
    missing_command = UpdateCameraCommand(
        camera_id=missing_id,
        name="Camera",
        ip_address="192.0.2.1",
        rtsp_port=554,
        username="operator",
        password=CAMERA_LEAK_SENTINEL,
        sources=(),
    )
    with pytest.raises(CameraNotFoundError):
        await update_camera(
            missing_command,
            uow=missing_uow,
            stream_gateway=gateway,
            id_generator=FixedIdGenerator(()),
            clock=FixedClock(UPDATED_AT),
        )
    assert missing_uow.rollback_count == 1

    corrupted_uow = FakeCameraUnitOfWork(FakeCameraStore())
    corrupted_uow.cameras.get_error = CameraAggregateCorruptedError(
        CameraFieldError(
            field="sources[0].url_suffix",
            code=CameraDomainErrorCode.CAMERA_AGGREGATE_INVALID,
            detail="受控损坏详情",
        )
    )
    with pytest.raises(CameraAggregateInvalidError) as captured:
        await update_camera(
            missing_command,
            uow=corrupted_uow,
            stream_gateway=gateway,
            id_generator=FixedIdGenerator(()),
            clock=FixedClock(UPDATED_AT),
        )
    assert captured.value.__context__ is None
    assert corrupted_uow.rollback_count == 1
    assert gateway.ensure_calls == []
    assert gateway.release_calls == []
    assert gateway.runtime_snapshot_count == 0


async def test_update_camera_rolls_back_save_failure_before_media() -> None:
    """完整保存失败恢复旧聚合，不能执行任何提交后副作用。"""

    camera = CameraBuilder().build(source_count=3)
    store = await store_camera(camera)
    uow = FakeCameraUnitOfWork(store)
    uow.cameras.save_error = CameraPersistenceOperationError()
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))

    with pytest.raises(CameraPersistenceOperationError):
        await update_camera(
            replacement_command(camera),
            uow=uow,
            stream_gateway=gateway,
            id_generator=FixedIdGenerator((NEW_SOURCE_ID,)),
            clock=FixedClock(UPDATED_AT),
        )

    assert uow.rollback_count == 1
    assert uow.commit_count == 0
    assert await FakeCameraUnitOfWork(store).cameras.get(camera.camera_id) == camera
    assert gateway.ensure_calls == []
    assert gateway.release_calls == []
    assert gateway.runtime_snapshot_count == 0


class CancellingCommitUnitOfWork(FakeCameraUnitOfWork):
    """模拟请求在数据库提交阶段取消且尚未发布 Fake 工作副本。"""

    async def commit(self) -> None:
        self.commit_count += 1
        raise asyncio.CancelledError


async def test_update_camera_rolls_back_commit_cancellation_without_media() -> None:
    """提交前取消原样传播，旧聚合仍是已提交事实。"""

    camera = CameraBuilder().build(source_count=3)
    store = await store_camera(camera)
    uow = CancellingCommitUnitOfWork(store)
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))

    with pytest.raises(asyncio.CancelledError):
        await update_camera(
            replacement_command(camera),
            uow=uow,
            stream_gateway=gateway,
            id_generator=FixedIdGenerator((NEW_SOURCE_ID,)),
            clock=FixedClock(UPDATED_AT),
        )

    assert uow.rollback_count == 1
    assert await FakeCameraUnitOfWork(store).cameras.get(camera.camera_id) == camera
    assert gateway.ensure_calls == []
    assert gateway.release_calls == []
    assert gateway.runtime_snapshot_count == 0


async def test_update_camera_propagates_post_commit_cancel_without_reverting_database() -> None:
    """媒体阶段取消不会被降级为 200，也不会撤销已经提交的新聚合。"""

    camera = CameraBuilder().build(source_count=3)
    store = await store_camera(camera)
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))
    gateway.ensure_failures[camera.sources[1].source_id] = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await update_camera(
            replacement_command(camera),
            uow=FakeCameraUnitOfWork(store),
            stream_gateway=gateway,
            id_generator=FixedIdGenerator((NEW_SOURCE_ID,)),
            clock=FixedClock(UPDATED_AT),
        )

    persisted = await FakeCameraUnitOfWork(store).cameras.get(camera.camera_id)
    assert persisted is not None
    assert tuple(source.source_id for source in persisted.sources) == (
        camera.sources[1].source_id,
        NEW_SOURCE_ID,
    )
    assert gateway.runtime_snapshot_count == 0


def test_update_command_and_result_inputs_are_hidden_from_default_repr() -> None:
    """密码和 Source 后缀不能通过命令默认表示进入意外日志。"""

    camera = CameraBuilder().build(source_count=3)
    command = replacement_command(camera)

    assert CAMERA_LEAK_SENTINEL not in repr(command)
    assert command.sources[0].url_suffix not in repr(command)
    assert command.sources[0].url_suffix not in repr(command.sources[0])
