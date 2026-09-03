"""Camera 默认预览源 Application 的事务与错误边界测试。"""

import asyncio
from datetime import UTC, datetime

import pytest

from app.modules.cameras.application import (
    CameraAggregateInvalidError,
    CameraNotFoundError,
    CameraPersistenceOperationError,
    SetDefaultPreviewSourceCommand,
    set_default_preview_source,
)
from app.modules.cameras.domain import (
    Camera,
    CameraAggregateCorruptedError,
    CameraDomainErrorCode,
    CameraFieldError,
    CameraValidationError,
)
from tests.support.cameras.builders import CameraBuilder, FixedClock, uuid4_from_index
from tests.support.cameras.fakes import FakeCameraStore, FakeCameraUnitOfWork

pytestmark = pytest.mark.anyio

UPDATED_AT = datetime(2026, 9, 2, 10, 0, tzinfo=UTC)


async def store_camera(camera: Camera) -> FakeCameraStore:
    """通过 Fake UoW 提交初始聚合，测试不绕过正式 Repository Port。"""

    store = FakeCameraStore()
    writer = FakeCameraUnitOfWork(store)
    await writer.cameras.add(camera)
    await writer.commit()
    return store


def command_for(camera: Camera, source_index: int) -> SetDefaultPreviewSourceCommand:
    """构造只携带 Camera/Source ID 的非敏感命令。"""

    return SetDefaultPreviewSourceCommand(
        camera_id=camera.camera_id,
        source_id=camera.sources[source_index].source_id,
    )


async def test_设置默认预览源保存完整聚合且不依赖运行时状态() -> None:
    """任意所属 Source 都能切换；用例只执行锁定读取、完整保存和提交。"""

    camera = CameraBuilder().build(source_count=2)
    store = await store_camera(camera)
    operation_log: list[str] = []
    uow = FakeCameraUnitOfWork(store, operation_log=operation_log)

    result = await set_default_preview_source(
        command_for(camera, 1),
        uow=uow,
        clock=FixedClock(UPDATED_AT),
    )

    assert result.camera_id == camera.camera_id
    assert result.default_preview_source_id == camera.sources[1].source_id
    assert result.updated_at == UPDATED_AT
    assert operation_log == [
        f"repository.get:{camera.camera_id}:True",
        f"repository.save:{camera.camera_id}",
        "uow.commit",
    ]

    persisted = await FakeCameraUnitOfWork(store).cameras.get(camera.camera_id)
    assert persisted is not None
    assert persisted.default_preview_source_id == camera.sources[1].source_id
    assert persisted.updated_at == UPDATED_AT
    # 切换默认源不能顺带修改 Source 配置、顺序或各 Source 的更新时间。
    assert persisted.sources == camera.sources


async def test_重复选择当前默认源仍推进Camera更新时间() -> None:
    """重复选择不是 no-op，仍保存并提交一次明确写请求。"""

    camera = CameraBuilder().build(source_count=2)
    store = await store_camera(camera)
    uow = FakeCameraUnitOfWork(store)

    result = await set_default_preview_source(
        command_for(camera, 0),
        uow=uow,
        clock=FixedClock(UPDATED_AT),
    )

    assert result.default_preview_source_id == camera.default_preview_source_id
    assert result.updated_at == UPDATED_AT
    assert uow.commit_count == 1
    persisted = await FakeCameraUnitOfWork(store).cameras.get(camera.camera_id)
    assert persisted is not None
    assert persisted.sources == camera.sources
    assert persisted.updated_at == UPDATED_AT


async def test_选择其他Camera的视频源时回滚且不保存() -> None:
    """不存在或属于其他 Camera 的 Source 返回稳定字段错误，并释放行锁事务。"""

    camera = CameraBuilder().build(source_count=2)
    uow = FakeCameraUnitOfWork(await store_camera(camera))
    command = SetDefaultPreviewSourceCommand(
        camera_id=camera.camera_id,
        source_id=uuid4_from_index(999),
    )

    with pytest.raises(CameraValidationError) as captured:
        await set_default_preview_source(
            command,
            uow=uow,
            clock=FixedClock(UPDATED_AT),
        )

    assert [(item.field, item.code.value) for item in captured.value.errors] == [
        ("source_id", "SOURCE_NOT_OWNED_BY_CAMERA")
    ]
    assert uow.rollback_count == 1
    assert uow.commit_count == 0
    assert not any(item.startswith("repository.save:") for item in uow.operation_log)


async def test_Camera缺失或损坏时结束事务并返回安全错误() -> None:
    """404 与损坏聚合 500 都在写入前结束事务，且损坏 issues 不进入应用错误。"""

    camera = CameraBuilder().build(source_count=2)
    command = command_for(camera, 1)

    missing_uow = FakeCameraUnitOfWork(FakeCameraStore())
    with pytest.raises(CameraNotFoundError):
        await set_default_preview_source(
            command,
            uow=missing_uow,
            clock=FixedClock(UPDATED_AT),
        )
    assert missing_uow.rollback_count == 1

    corrupted_uow = FakeCameraUnitOfWork(FakeCameraStore())
    corrupted_uow.cameras.get_error = CameraAggregateCorruptedError(
        CameraFieldError(
            field="sources[0].url_suffix",
            code=CameraDomainErrorCode.CAMERA_AGGREGATE_INVALID,
            detail="不应进入公开错误的损坏详情",
        )
    )
    with pytest.raises(CameraAggregateInvalidError) as captured:
        await set_default_preview_source(
            command,
            uow=corrupted_uow,
            clock=FixedClock(UPDATED_AT),
        )
    assert captured.value.__context__ is None
    assert corrupted_uow.rollback_count == 1


@pytest.mark.parametrize("failure_stage", ["get", "save", "commit"])
async def test_数据库失败时回滚未提交的默认源变更(failure_stage: str) -> None:
    """读取、保存或提交失败都恢复旧聚合，并向上保留数据库不可用错误。"""

    camera = CameraBuilder().build(source_count=2)
    store = await store_camera(camera)

    uow = FakeCameraUnitOfWork(store)
    if failure_stage == "commit":
        uow.commit_error = CameraPersistenceOperationError()
    if failure_stage == "save":
        uow.cameras.save_error = CameraPersistenceOperationError()
    if failure_stage == "get":
        uow.cameras.get_error = CameraPersistenceOperationError()

    with pytest.raises(CameraPersistenceOperationError):
        await set_default_preview_source(
            command_for(camera, 1),
            uow=uow,
            clock=FixedClock(UPDATED_AT),
        )

    assert uow.rollback_count == 1
    persisted = await FakeCameraUnitOfWork(store).cameras.get(camera.camera_id)
    assert persisted == camera


async def test_提交取消时继续抛出并回滚工作副本() -> None:
    """提交阶段取消不改写为业务成功，且尽力清理尚未提交的修改。"""

    camera = CameraBuilder().build(source_count=2)
    store = await store_camera(camera)

    uow = FakeCameraUnitOfWork(store)
    uow.commit_error = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await set_default_preview_source(
            command_for(camera, 1),
            uow=uow,
            clock=FixedClock(UPDATED_AT),
        )

    assert uow.rollback_count == 1
    assert await FakeCameraUnitOfWork(store).cameras.get(camera.camera_id) == camera


async def test_服务器时钟约束错误不被误报为持久化数据损坏() -> None:
    """领域阶段的服务端时钟错误仍是内部错误，不转换成 CAMERA_AGGREGATE_INVALID。"""

    camera = CameraBuilder().build(source_count=2)
    uow = FakeCameraUnitOfWork(await store_camera(camera))

    with pytest.raises(CameraAggregateCorruptedError):
        await set_default_preview_source(
            command_for(camera, 1),
            uow=uow,
            clock=FixedClock(datetime(2020, 1, 1, tzinfo=UTC)),
        )

    assert uow.rollback_count == 1
    assert uow.commit_count == 0
