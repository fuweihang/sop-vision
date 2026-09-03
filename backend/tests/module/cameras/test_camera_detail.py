"""Camera 详情 Application 用例的只读事务、状态投影与错误边界测试。"""

import asyncio
import logging
from datetime import UTC, datetime

import pytest

from app.modules.cameras.application import (
    CameraAggregateInvalidError,
    CameraNotFoundError,
    CameraPersistenceOperationError,
    CameraStatus,
    get_camera_detail,
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
from tests.support.cameras.builders import CameraBuilder, FixedClock, uuid4_from_index
from tests.support.cameras.constants import CAMERA_LEAK_SENTINEL
from tests.support.cameras.fakes import (
    FakeCameraStore,
    FakeCameraUnitOfWork,
    FakeStreamGateway,
)

pytestmark = pytest.mark.anyio

SNAPSHOT_AT = datetime(2026, 8, 28, 9, 0, tzinfo=UTC)
FAILED_AT = datetime(2026, 8, 28, 9, 0, 1, tzinfo=UTC)


async def committed_reader(
    camera: Camera,
    operation_log: list[str] | None = None,
) -> FakeCameraUnitOfWork:
    """把聚合写入 Fake 的已提交快照，再返回只用于详情读取的新 UoW。"""

    store = FakeCameraStore()
    writer = FakeCameraUnitOfWork(store)
    await writer.cameras.add(camera)
    await writer.commit()
    return FakeCameraUnitOfWork(store, operation_log=operation_log)


@pytest.mark.parametrize(
    ("online_flags", "expected_status", "expected_online"),
    [
        ((True, True), CameraStatus.ONLINE, 2),
        ((False, False), CameraStatus.OFFLINE, 0),
        ((True, False), CameraStatus.DEGRADED, 1),
    ],
)
async def test_详情查询只读取一次快照并复用Camera状态规则(
    online_flags: tuple[bool, bool],
    expected_status: CameraStatus,
    expected_online: int,
) -> None:
    """全在线、全离线和混合详情都复用一次快照及共享 Camera 状态统计。"""

    camera = CameraBuilder().build(source_count=2)
    paths = tuple(
        RuntimePath(name=str(source.source_id), available=True, online=True)
        for source, online in zip(camera.sources, online_flags, strict=True)
        if online
    )
    operation_log: list[str] = []
    uow = await committed_reader(camera, operation_log)
    gateway = FakeStreamGateway(
        RuntimePathSnapshot(paths=paths, checked_at=SNAPSHOT_AT),
        operation_log=operation_log,
    )
    clock = FixedClock(FAILED_AT)

    result = await get_camera_detail(
        camera.camera_id,
        uow=uow,
        stream_gateway=gateway,
        clock=clock,
    )

    assert result.camera == camera
    assert result.runtime_summary.status is expected_status
    assert result.runtime_summary.online_source_count == expected_online
    assert result.runtime_summary.source_count == 2
    assert tuple(item.source_id for item in result.source_runtime) == tuple(
        source.source_id for source in camera.sources
    )
    assert gateway.runtime_snapshot_count == 1
    assert gateway.ensure_calls == []
    assert clock.now_count == 0
    assert uow.commit_count == 0
    assert uow.rollback_count == 1
    assert operation_log == [
        f"repository.get:{camera.camera_id}:False",
        "uow.rollback",
        "stream_gateway.fetch_runtime_path_snapshot",
    ]


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
async def test_详情查询结束事务后对已知网关失败返回降级结果(
    gateway_error: Exception,
    expected_code: SourceRuntimeErrorCode,
) -> None:
    """两类受支持媒体故障使用一次失败时间返回 200 所需的全离线投影。"""

    camera = CameraBuilder().build(source_count=2)
    operation_log: list[str] = []
    uow = await committed_reader(camera, operation_log)
    gateway = FakeStreamGateway(gateway_error, operation_log=operation_log)
    clock = FixedClock(FAILED_AT)

    result = await get_camera_detail(
        camera.camera_id,
        uow=uow,
        stream_gateway=gateway,
        clock=clock,
    )

    assert result.runtime_summary.status is CameraStatus.OFFLINE
    assert {item.error for item in result.source_runtime} == {expected_code}
    assert all(item.last_checked_at == FAILED_AT for item in result.source_runtime)
    assert all(item.whep_url is None for item in result.source_runtime)
    assert clock.now_count == 1
    assert gateway.runtime_snapshot_count == 1
    assert gateway.ensure_calls == []
    assert operation_log[-2:] == [
        "uow.rollback",
        "stream_gateway.fetch_runtime_path_snapshot",
    ]


async def test_详情查询未找到时结束事务且不访问网关() -> None:
    """Camera 不存在时返回准确 ID，且不为无效目标请求 MediaMTX 全量快照。"""

    camera_id = uuid4_from_index(999)
    uow = FakeCameraUnitOfWork(FakeCameraStore())
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))

    with pytest.raises(CameraNotFoundError) as captured:
        await get_camera_detail(
            camera_id,
            uow=uow,
            stream_gateway=gateway,
            clock=FixedClock(FAILED_AT),
        )

    assert captured.value.camera_id == camera_id
    assert str(camera_id) not in repr(captured.value)
    assert uow.rollback_count == 1
    assert gateway.runtime_snapshot_count == 0
    assert gateway.ensure_calls == []


async def test_详情查询继续抛出数据库失败且不访问网关() -> None:
    """数据库读取失败必须保留应用层错误，不能伪装成不存在或媒体离线。"""

    camera_id = uuid4_from_index(778)
    uow = FakeCameraUnitOfWork(FakeCameraStore())
    uow.cameras.get_error = CameraPersistenceOperationError()
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))

    with pytest.raises(CameraPersistenceOperationError):
        await get_camera_detail(
            camera_id,
            uow=uow,
            stream_gateway=gateway,
            clock=FixedClock(FAILED_AT),
        )

    # Repository 错误发生后不能继续访问媒体端口；事务清理由请求级 Session dependency 负责。
    assert gateway.runtime_snapshot_count == 0


@pytest.mark.sensitive_data
async def test_详情查询将损坏聚合转换为安全错误且只记录一条日志(caplog) -> None:
    """领域损坏项不会进入应用错误、HTTP 可见消息或已注册业务日志。"""

    camera_id = uuid4_from_index(777)
    uow = FakeCameraUnitOfWork(FakeCameraStore())
    uow.cameras.get_error = CameraAggregateCorruptedError(
        CameraFieldError(
            field="url_suffix",
            code=CameraDomainErrorCode.CAMERA_AGGREGATE_INVALID,
            detail=f"损坏值包含 {CAMERA_LEAK_SENTINEL}",
        )
    )
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))

    with caplog.at_level(logging.ERROR, logger="app.modules.cameras.application.detail"):
        with pytest.raises(CameraAggregateInvalidError) as captured:
            await get_camera_detail(
                camera_id,
                uow=uow,
                stream_gateway=gateway,
                clock=FixedClock(FAILED_AT),
            )

    assert captured.value.camera_id == camera_id
    assert captured.value.__context__ is None
    assert CAMERA_LEAK_SENTINEL not in repr(captured.value)
    assert uow.rollback_count == 1
    assert gateway.runtime_snapshot_count == 0
    records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "camera.detail_aggregate_invalid"
    ]
    assert len(records) == 1
    assert records[0].levelno == logging.ERROR
    assert records[0].operation == "get_camera"
    assert records[0].outcome == "failed"
    assert records[0].camera_id == str(camera_id)
    assert CAMERA_LEAK_SENTINEL not in caplog.text


@pytest.mark.parametrize("cancel_stage", ["database", "gateway"])
async def test_详情查询继续抛出任务取消(cancel_stage: str) -> None:
    """任务取消不能被媒体降级或应用错误转换吞掉。"""

    camera = CameraBuilder().build(source_count=1)
    uow = await committed_reader(camera)
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))
    if cancel_stage == "database":
        uow.cameras.get_error = asyncio.CancelledError()
    else:

        async def cancel_snapshot() -> RuntimePathSnapshot:
            raise asyncio.CancelledError

        gateway.fetch_runtime_path_snapshot = cancel_snapshot  # type: ignore[method-assign]

    with pytest.raises(asyncio.CancelledError):
        await get_camera_detail(
            camera.camera_id,
            uow=uow,
            stream_gateway=gateway,
            clock=FixedClock(FAILED_AT),
        )

    if cancel_stage == "database":
        # 请求级 Session dependency 会处理未捕获取消；应用服务不得把取消改写为数据库错误。
        assert uow.rollback_count == 0
    else:
        assert uow.rollback_count == 1
    assert gateway.ensure_calls == []


async def test_详情查询结束事务后继续抛出未知网关错误() -> None:
    """未知程序错误不能为了返回部分详情而被当成媒体不可用。"""

    camera = CameraBuilder().build(source_count=1)
    uow = await committed_reader(camera)
    gateway = FakeStreamGateway(RuntimeError("测试未知错误"))

    with pytest.raises(RuntimeError, match="测试未知错误"):
        await get_camera_detail(
            camera.camera_id,
            uow=uow,
            stream_gateway=gateway,
            clock=FixedClock(FAILED_AT),
        )

    assert uow.rollback_count == 1
    assert gateway.ensure_calls == []
