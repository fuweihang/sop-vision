"""Camera 列表 Application 用例的分页、事务、批量投影和安全错误测试。"""

import asyncio
import logging
from datetime import UTC, datetime

import pytest

from app.modules.cameras.application import (
    CameraListAggregateInvalidError,
    CameraListCriteria,
    CameraPersistenceOperationError,
    CameraStatus,
    list_cameras,
)
from app.modules.cameras.domain import (
    Camera,
    CameraAggregateCorruptedError,
    CameraDomainErrorCode,
    CameraFieldError,
)
from app.modules.stream_gateway.ports import (
    RuntimePath,
    RuntimePathSnapshot,
    SourceRuntimeErrorCode,
    StreamGatewayInvalidResponseError,
    StreamGatewayUnavailableError,
)
from tests.modules.cameras.builders import CameraBuilder, FixedClock
from tests.modules.cameras.constants import CAMERA_LEAK_SENTINEL
from tests.modules.cameras.fakes import (
    FakeCameraStore,
    FakeCameraUnitOfWork,
    FakeStreamGateway,
)

pytestmark = pytest.mark.anyio

SNAPSHOT_AT = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
FAILED_AT = datetime(2026, 9, 1, 8, 0, 1, tzinfo=UTC)


async def committed_reader(
    cameras: tuple[Camera, ...],
    operation_log: list[str] | None = None,
) -> FakeCameraUnitOfWork:
    """正常提交多条聚合，再返回绑定同一已提交快照的列表读取 UoW。"""

    store = FakeCameraStore()
    writer = FakeCameraUnitOfWork(store)
    for camera in cameras:
        await writer.cameras.add(camera)
    await writer.commit()
    return FakeCameraUnitOfWork(store, operation_log=operation_log)


def build_status_cameras() -> tuple[Camera, Camera, Camera]:
    """构造全在线、全离线和混合三条 Camera，ID 范围互不重叠。"""

    return (
        CameraBuilder().build(source_count=2, id_start=100),
        CameraBuilder().build(source_count=2, id_start=200),
        CameraBuilder().build(source_count=2, id_start=300),
    )


async def test_list_uses_count_then_page_ends_transaction_and_projects_one_snapshot() -> None:
    """一页多 Camera 只读取一次快照，并在媒体 I/O 前结束只读事务。"""

    cameras = build_status_cameras()
    online_camera, offline_camera, mixed_camera = cameras
    # 全在线 Camera 放两条 Path；混合 Camera 只放第一路；离线 Camera 不放 Path。
    online_source_ids = tuple(source.source_id for source in online_camera.sources)
    mixed_online_id = mixed_camera.sources[0].source_id
    paths = tuple(
        RuntimePath(name=str(source_id), available=True, online=True)
        for source_id in (*online_source_ids, mixed_online_id)
    )
    operation_log: list[str] = []
    uow = await committed_reader(cameras, operation_log)
    gateway = FakeStreamGateway(
        RuntimePathSnapshot(paths=paths, checked_at=SNAPSHOT_AT),
        operation_log=operation_log,
    )

    result = await list_cameras(
        CameraListCriteria(),
        1,
        20,
        uow=uow,
        stream_gateway=gateway,
        clock=FixedClock(FAILED_AT),
    )

    assert result.total == 3
    assert result.page == 1
    assert result.page_size == 20
    assert [item.runtime_summary.status for item in result.items] == [
        CameraStatus.ONLINE,
        CameraStatus.OFFLINE,
        CameraStatus.DEGRADED,
    ]
    assert [item.runtime_summary.online_source_count for item in result.items] == [2, 0, 1]
    assert gateway.runtime_snapshot_count == 1
    assert gateway.ensure_calls == []
    assert uow.commit_count == 0
    assert uow.rollback_count == 1
    assert operation_log == [
        "repository.count:None",
        "repository.list:None:1:20",
        "uow.rollback",
        "stream_gateway.fetch_runtime_path_snapshot",
    ]


async def test_list_empty_page_returns_real_total_without_accessing_gateway() -> None:
    """越界页仍返回 count，总页内容为空时不执行无意义的媒体快照。"""

    cameras = (CameraBuilder().build(source_count=1, id_start=400),)
    uow = await committed_reader(cameras)
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))

    result = await list_cameras(
        CameraListCriteria(),
        2,
        20,
        uow=uow,
        stream_gateway=gateway,
        clock=FixedClock(FAILED_AT),
    )

    assert result.items == ()
    assert result.total == 1
    assert result.page == 2
    assert uow.rollback_count == 1
    assert gateway.runtime_snapshot_count == 0


@pytest.mark.parametrize(
    ("gateway_error", "expected_code"),
    [
        (StreamGatewayUnavailableError(), SourceRuntimeErrorCode.CONTROL_API_UNAVAILABLE),
        (
            StreamGatewayInvalidResponseError(),
            SourceRuntimeErrorCode.CONTROL_API_INVALID_RESPONSE,
        ),
    ],
)
async def test_list_degrades_supported_gateway_failures_with_one_page_timestamp(
    gateway_error: Exception,
    expected_code: SourceRuntimeErrorCode,
) -> None:
    """两类已知媒体故障不改变 200 配置结果，整页 Source 共用一次失败时间。"""

    cameras = (
        CameraBuilder().build(source_count=2, id_start=500),
        CameraBuilder().build(source_count=1, id_start=600),
    )
    uow = await committed_reader(cameras)
    gateway = FakeStreamGateway(gateway_error)
    clock = FixedClock(FAILED_AT)

    result = await list_cameras(
        CameraListCriteria(),
        1,
        20,
        uow=uow,
        stream_gateway=gateway,
        clock=clock,
    )

    projections = tuple(projection for item in result.items for projection in item.source_runtime)
    assert {item.runtime_summary.status for item in result.items} == {CameraStatus.OFFLINE}
    assert {projection.error for projection in projections} == {expected_code}
    assert {projection.last_checked_at for projection in projections} == {FAILED_AT}
    assert all(projection.whep_url is None for projection in projections)
    assert clock.now_count == 1
    assert gateway.runtime_snapshot_count == 1


@pytest.mark.sensitive_data
async def test_list_converts_corruption_to_error_without_identity_or_exception_context(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """批量损坏不公开条目身份、领域 issue 或敏感内容，并且不访问媒体服务。"""

    uow = FakeCameraUnitOfWork(FakeCameraStore())
    uow.cameras.list_error = CameraAggregateCorruptedError(
        CameraFieldError(
            field="password",
            code=CameraDomainErrorCode.CAMERA_AGGREGATE_INVALID,
            detail=f"损坏字段包含 {CAMERA_LEAK_SENTINEL}",
        )
    )
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))

    with caplog.at_level(logging.ERROR, logger="app.modules.cameras.application.listing"):
        with pytest.raises(CameraListAggregateInvalidError) as captured:
            await list_cameras(
                CameraListCriteria(),
                1,
                20,
                uow=uow,
                stream_gateway=gateway,
                clock=FixedClock(FAILED_AT),
            )

    assert not hasattr(captured.value, "camera_id")
    assert captured.value.__context__ is None
    assert CAMERA_LEAK_SENTINEL not in repr(captured.value)
    assert uow.rollback_count == 1
    assert gateway.runtime_snapshot_count == 0
    records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "camera.list_aggregate_invalid"
    ]
    assert len(records) == 1
    assert records[0].operation == "list_cameras"
    assert records[0].outcome == "failed"
    assert not hasattr(records[0], "camera_id")
    assert CAMERA_LEAK_SENTINEL not in caplog.text


@pytest.mark.parametrize("failure_stage", ["count", "list"])
async def test_list_propagates_database_failure_without_media_access(failure_stage: str) -> None:
    """count 或分页读取失败都保持数据库 503 语义，不能降级成空列表。"""

    uow = FakeCameraUnitOfWork(FakeCameraStore())
    if failure_stage == "count":
        uow.cameras.count_error = CameraPersistenceOperationError()
    else:
        uow.cameras.list_error = CameraPersistenceOperationError()
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))

    with pytest.raises(CameraPersistenceOperationError):
        await list_cameras(
            CameraListCriteria(),
            1,
            20,
            uow=uow,
            stream_gateway=gateway,
            clock=FixedClock(FAILED_AT),
        )

    assert gateway.runtime_snapshot_count == 0


@pytest.mark.parametrize("cancel_stage", ["database", "gateway"])
async def test_list_propagates_task_cancellation(cancel_stage: str) -> None:
    """数据库或媒体阶段的任务取消不能被转换成业务错误或 200 降级。"""

    camera = CameraBuilder().build(source_count=1, id_start=700)
    uow = await committed_reader((camera,))
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))
    if cancel_stage == "database":
        uow.cameras.count_error = asyncio.CancelledError()
    else:

        async def cancel_snapshot() -> RuntimePathSnapshot:
            raise asyncio.CancelledError

        gateway.fetch_runtime_path_snapshot = cancel_snapshot  # type: ignore[method-assign]

    with pytest.raises(asyncio.CancelledError):
        await list_cameras(
            CameraListCriteria(),
            1,
            20,
            uow=uow,
            stream_gateway=gateway,
            clock=FixedClock(FAILED_AT),
        )

    assert gateway.ensure_calls == []


async def test_list_propagates_unknown_gateway_error_after_ending_transaction() -> None:
    """未知媒体程序错误不能伪装成离线列表。"""

    camera = CameraBuilder().build(source_count=1, id_start=800)
    uow = await committed_reader((camera,))
    gateway = FakeStreamGateway(RuntimeError("测试未知错误"))

    with pytest.raises(RuntimeError, match="测试未知错误"):
        await list_cameras(
            CameraListCriteria(),
            1,
            20,
            uow=uow,
            stream_gateway=gateway,
            clock=FixedClock(FAILED_AT),
        )

    assert uow.rollback_count == 1
