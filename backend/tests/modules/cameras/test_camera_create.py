"""Camera 创建 Application 用例的事务与媒体编排测试。"""

import asyncio
from datetime import UTC, datetime

import pytest

from app.modules.cameras.application import (
    CameraPersistenceOperationError,
    CameraStatus,
    CreateCameraCommand,
    CreateCameraSourceCommand,
    create_camera,
)
from app.modules.stream_gateway.ports import (
    RuntimePath,
    RuntimePathSnapshot,
    SourceRuntimeErrorCode,
    StreamGatewayInvalidResponseError,
    StreamGatewayUnavailableError,
)
from tests.modules.cameras.builders import FixedClock, FixedIdGenerator, uuid4_from_index
from tests.modules.cameras.fakes import (
    FakeCameraStore,
    FakeCameraUnitOfWork,
    FakeStreamGateway,
)

pytestmark = pytest.mark.anyio

CREATED_AT = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)
SNAPSHOT_AT = datetime(2026, 8, 27, 8, 0, 1, tzinfo=UTC)


def make_command(source_count: int) -> CreateCameraCommand:
    """生成按第一路为默认源的确定创建命令。"""

    return CreateCameraCommand(
        name=" 洗手区 01 ",
        ip_address="192.0.2.64",
        rtsp_port=554,
        username="operator name",
        password="camera-create-test-password",
        sources=tuple(
            CreateCameraSourceCommand(
                name=f" 视频源 {index + 1} ",
                url_suffix=f" /Streaming/Channels/{index + 1:03d} ",
                is_default_preview=index == 0,
            )
            for index in range(source_count)
        ),
    )


def fixed_ids(source_count: int, *, start: int = 1) -> FixedIdGenerator:
    """Camera ID 在前，后续 ID 按请求 Source 顺序生成。"""

    return FixedIdGenerator(
        uuid4_from_index(index) for index in range(start, start + source_count + 1)
    )


@pytest.mark.parametrize("source_count", [1, 2, 10])
async def test_create_camera_commits_complete_aggregate_before_media(
    source_count: int,
) -> None:
    """单、双、十路创建都一次提交，并按 Source 顺序同步及返回离线投影。"""

    store = FakeCameraStore()
    uow = FakeCameraUnitOfWork(store)
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))
    command = make_command(source_count)

    result = await create_camera(
        command,
        uow=uow,
        stream_gateway=gateway,
        id_generator=fixed_ids(source_count),
        clock=FixedClock(CREATED_AT),
    )

    assert uow.commit_count == 1
    assert uow.rollback_count == 0
    assert result.camera.name == "洗手区 01"
    assert result.camera.created_at == result.camera.updated_at == CREATED_AT
    assert tuple(source.sort_order for source in result.camera.sources) == tuple(
        range(source_count)
    )
    assert tuple(source.url_suffix for source in result.camera.sources) == tuple(
        f"Streaming/Channels/{index + 1:03d}" for index in range(source_count)
    )
    assert result.camera.default_preview_source_id == result.camera.sources[0].source_id
    assert tuple(item.source_id for item in gateway.ensure_calls) == tuple(
        source.source_id for source in result.camera.sources
    )
    assert gateway.runtime_snapshot_count == 1
    assert result.runtime_summary.status is CameraStatus.OFFLINE
    assert result.runtime_summary.online_source_count == 0
    assert result.runtime_summary.source_count == source_count
    assert all(item.last_checked_at == SNAPSHOT_AT for item in result.source_runtime)
    assert all(item.whep_url is None for item in result.source_runtime)
    assert command.password not in repr(result)
    assert command.sources[0].url_suffix not in repr(result)

    # 新建另一个 UoW 从已提交快照读取，证明 Fake 中不是只有当前工作副本可见。
    reader = FakeCameraUnitOfWork(store)
    assert await reader.cameras.get(result.camera.camera_id) == result.camera


async def test_create_camera_continues_after_one_ensure_failure_and_uses_one_snapshot() -> None:
    """单路即时同步失败不会阻塞后续 Source，状态只使用同步后的同一份快照。"""

    first_source_id = uuid4_from_index(2)
    second_source_id = uuid4_from_index(3)
    gateway = FakeStreamGateway(
        RuntimePathSnapshot(
            paths=(RuntimePath(name=str(second_source_id), available=True, online=True),),
            checked_at=SNAPSHOT_AT,
        )
    )
    gateway.ensure_failures[first_source_id] = StreamGatewayUnavailableError()

    result = await create_camera(
        make_command(2),
        uow=FakeCameraUnitOfWork(FakeCameraStore()),
        stream_gateway=gateway,
        id_generator=fixed_ids(2),
        clock=FixedClock(CREATED_AT),
    )

    assert tuple(item.source_id for item in gateway.ensure_calls) == (
        first_source_id,
        second_source_id,
    )
    assert gateway.runtime_snapshot_count == 1
    assert result.runtime_summary.status is CameraStatus.DEGRADED
    assert result.runtime_summary.online_source_count == 1
    assert result.source_runtime[0].error is SourceRuntimeErrorCode.PATH_NOT_FOUND
    assert result.source_runtime[1].whep_url == (
        f"https://media.example.invalid/{second_source_id}/whep"
    )


@pytest.mark.parametrize(
    ("gateway_error", "expected_code"),
    [
        (StreamGatewayUnavailableError(), SourceRuntimeErrorCode.CONTROL_API_UNAVAILABLE),
        (StreamGatewayInvalidResponseError(), SourceRuntimeErrorCode.CONTROL_API_INVALID_RESPONSE),
    ],
)
async def test_create_camera_degrades_snapshot_failure_after_commit(
    gateway_error: Exception,
    expected_code: SourceRuntimeErrorCode,
) -> None:
    """两类受支持快照故障都返回同一完成时间下的全离线投影。"""

    clock = FixedClock(CREATED_AT)
    gateway = FakeStreamGateway(gateway_error)
    uow = FakeCameraUnitOfWork(FakeCameraStore())

    # Camera.create 先读取创建时间；快照失败前推进 Clock，证明降级投影读取的是故障完成时间。
    original_commit = uow.commit

    async def commit_and_advance_clock() -> None:
        await original_commit()
        clock.set(SNAPSHOT_AT)

    uow.commit = commit_and_advance_clock  # type: ignore[method-assign]
    result = await create_camera(
        make_command(2),
        uow=uow,
        stream_gateway=gateway,
        id_generator=fixed_ids(2),
        clock=clock,
    )

    assert uow.commit_count == 1
    assert gateway.runtime_snapshot_count == 1
    assert result.runtime_summary.status is CameraStatus.OFFLINE
    assert all(item.error is expected_code for item in result.source_runtime)
    assert all(item.last_checked_at == SNAPSHOT_AT for item in result.source_runtime)


class CommitFailingUnitOfWork(FakeCameraUnitOfWork):
    """在发布 Fake 工作副本前模拟一次安全数据库提交失败。"""

    async def commit(self) -> None:
        self.commit_count += 1
        raise CameraPersistenceOperationError


async def test_create_camera_rolls_back_commit_failure_before_any_media_call() -> None:
    """提交失败必须恢复工作副本，且不能开始任何 MediaMTX I/O。"""

    store = FakeCameraStore()
    uow = CommitFailingUnitOfWork(store)
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))

    with pytest.raises(CameraPersistenceOperationError):
        await create_camera(
            make_command(2),
            uow=uow,
            stream_gateway=gateway,
            id_generator=fixed_ids(2),
            clock=FixedClock(CREATED_AT),
        )

    assert uow.commit_count == 1
    assert uow.rollback_count == 1
    assert gateway.ensure_calls == []
    assert gateway.runtime_snapshot_count == 0
    assert await FakeCameraUnitOfWork(store).cameras.get(uuid4_from_index(1)) is None


async def test_create_camera_does_not_swallow_unexpected_media_error_after_commit() -> None:
    """Port 约定外错误继续上抛，但已经提交的完整 Camera 不会被反向删除。"""

    store = FakeCameraStore()
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))
    gateway.ensure_failures[uuid4_from_index(2)] = RuntimeError("受控测试错误")

    with pytest.raises(RuntimeError, match="受控测试错误"):
        await create_camera(
            make_command(1),
            uow=FakeCameraUnitOfWork(store),
            stream_gateway=gateway,
            id_generator=fixed_ids(1),
            clock=FixedClock(CREATED_AT),
        )

    assert await FakeCameraUnitOfWork(store).cameras.get(uuid4_from_index(1)) is not None
    assert gateway.runtime_snapshot_count == 0


class CancellingCommitUnitOfWork(FakeCameraUnitOfWork):
    """模拟请求在数据库提交阶段收到任务取消。"""

    async def commit(self) -> None:
        self.commit_count += 1
        raise asyncio.CancelledError


async def test_create_camera_rolls_back_and_propagates_commit_cancellation() -> None:
    """取消不是业务错误；清理工作副本后必须原样传播。"""

    store = FakeCameraStore()
    uow = CancellingCommitUnitOfWork(store)
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))

    with pytest.raises(asyncio.CancelledError):
        await create_camera(
            make_command(1),
            uow=uow,
            stream_gateway=gateway,
            id_generator=fixed_ids(1),
            clock=FixedClock(CREATED_AT),
        )

    assert uow.rollback_count == 1
    assert gateway.ensure_calls == []
    assert await FakeCameraUnitOfWork(store).cameras.get(uuid4_from_index(1)) is None


def test_create_command_default_repr_does_not_expose_request_values() -> None:
    """命令的默认表示不能把密码或 Source 后缀带入意外日志。"""

    command = make_command(1)
    rendered = repr(command)

    assert command.password not in rendered
    assert command.sources[0].url_suffix not in rendered
