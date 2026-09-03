"""Camera 创建 Application 用例的事务与媒体编排测试。"""

import asyncio
import logging
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
from tests.support.cameras.builders import (
    FixedClock,
    FixedIdGenerator,
    SequenceClock,
    uuid4_from_index,
)
from tests.support.cameras.fakes import (
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


async def test_创建Camera时先提交完整聚合再调用媒体网关() -> None:
    """完整聚合一次提交后，按 Source 顺序同步并返回离线投影。"""

    # Source 数量边界已经由领域单元测试覆盖。模块测试固定为两路，专注检查事务提交、
    # 媒体同步和运行态投影之间的协作，避免按数量重复同一条应用流程。
    source_count = 2
    operation_log: list[str] = []
    store = FakeCameraStore()
    uow = FakeCameraUnitOfWork(store, operation_log=operation_log)
    gateway = FakeStreamGateway(
        RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT),
        operation_log=operation_log,
    )
    command = make_command(source_count)

    result = await create_camera(
        command,
        uow=uow,
        stream_gateway=gateway,
        id_generator=fixed_ids(source_count),
        clock=FixedClock(CREATED_AT),
    )

    source_ids = tuple(source.source_id for source in result.camera.sources)
    assert operation_log == [
        f"repository.add:{result.camera.camera_id}",
        "uow.commit",
        *(f"stream_gateway.ensure_path:{source_id}" for source_id in source_ids),
        "stream_gateway.fetch_runtime_path_snapshot",
    ]
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


async def test_创建Camera时单个确保失败后继续并只读取一次快照(
    caplog,
) -> None:
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
    command = make_command(2)

    with caplog.at_level(logging.WARNING, logger="app.modules.cameras.application.create"):
        result = await create_camera(
            command,
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
    record = next(
        record
        for record in caplog.records
        if record.name == "app.modules.cameras.application.create"
    )
    assert record.message == "Camera 已保存，但媒体操作未全部成功"
    assert record.event == "camera.media_sync_degraded"
    assert record.operation == "post_commit_media_sync"
    assert record.outcome == "degraded"
    assert record.camera_id == str(uuid4_from_index(1))
    assert record.failed_count == 1
    assert command.password not in caplog.text
    assert command.sources[0].url_suffix not in caplog.text


@pytest.mark.parametrize(
    ("gateway_error", "expected_code"),
    [
        (StreamGatewayUnavailableError(), SourceRuntimeErrorCode.CONTROL_API_UNAVAILABLE),
        (StreamGatewayInvalidResponseError(), SourceRuntimeErrorCode.CONTROL_API_INVALID_RESPONSE),
    ],
)
async def test_创建Camera提交后快照失败时返回降级结果(
    gateway_error: Exception,
    expected_code: SourceRuntimeErrorCode,
) -> None:
    """两类受支持快照故障都返回同一完成时间下的全离线投影。"""

    clock = SequenceClock((CREATED_AT, SNAPSHOT_AT))
    gateway = FakeStreamGateway(gateway_error)
    uow = FakeCameraUnitOfWork(FakeCameraStore())

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


async def test_创建Camera提交失败时回滚且不调用媒体网关() -> None:
    """提交失败必须恢复工作副本，且不能开始任何 MediaMTX I/O。"""

    store = FakeCameraStore()
    uow = FakeCameraUnitOfWork(store)
    uow.commit_error = CameraPersistenceOperationError()
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


async def test_创建Camera提交后不吞掉意外媒体错误() -> None:
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


async def test_创建Camera提交被取消时回滚并继续抛出() -> None:
    """取消不是业务错误；清理工作副本后必须原样传播。"""

    store = FakeCameraStore()
    uow = FakeCameraUnitOfWork(store)
    uow.commit_error = asyncio.CancelledError()
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
