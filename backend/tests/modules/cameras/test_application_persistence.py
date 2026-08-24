"""Camera 应用层端口、Fake 事务与持久化错误的快速契约测试。"""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cameras.api.dependencies import get_camera_unit_of_work
from app.modules.cameras.application import (
    CameraConstraintViolationError,
    CameraConstraintViolationKind,
    CameraListCriteria,
    CameraPersistenceOperationError,
)
from app.modules.cameras.application.ports import validate_camera_list_pagination
from app.modules.cameras.domain import Camera, CameraSourceChange
from app.modules.cameras.persistence.constraints import translate_integrity_error
from app.modules.cameras.persistence.mapper import camera_to_rows, rows_to_camera
from app.modules.cameras.persistence.uow import SQLAlchemyCameraUnitOfWork
from tests.modules.cameras.builders import (
    FIXED_TIME,
    CameraBuilder,
    CameraListBuilder,
    FixedClock,
    FixedIdGenerator,
    uuid4_from_index,
)
from tests.modules.cameras.fakes import FakeCameraStore, FakeCameraUnitOfWork
from tests.modules.cameras.repository_contract import assert_camera_repository_contract

pytestmark = pytest.mark.anyio


def _updated_camera_with_replacement_source() -> tuple[Camera, Camera]:
    camera = CameraBuilder().build(source_count=2)
    retained = camera.sources[1]
    updated = camera.update_configuration(
        name="更新后的 Camera",
        ip_address="192.168.1.65",
        rtsp_port=8554,
        username="updated-user",
        password="updated-secret",
        sources=(
            CameraSourceChange(
                source_id=retained.source_id,
                name="保留且重排的 Source",
                url_suffix="retained",
                is_default_preview=True,
            ),
            CameraSourceChange(
                name="新增 Source",
                url_suffix="new-source",
            ),
        ),
        id_generator=FixedIdGenerator((uuid4_from_index(99),)),
        clock=FixedClock(FIXED_TIME + timedelta(seconds=1)),
    )
    return camera, updated


def test_list_criteria_and_pagination_reject_non_normalized_boundaries() -> None:
    """所有 Repository 实现共享同一查询长度和分页上限。"""

    assert CameraListCriteria().q is None
    assert validate_camera_list_pagination(2, 20) == 20
    with pytest.raises(ValueError, match="规范化"):
        CameraListCriteria(q=" camera ")
    with pytest.raises(ValueError, match="100"):
        CameraListCriteria(q="x" * 101)
    with pytest.raises(ValueError, match="页码"):
        validate_camera_list_pagination(0, 20)
    with pytest.raises(ValueError, match="1-100"):
        validate_camera_list_pagination(1, 101)


def test_mapper_round_trip_preserves_complete_aggregate_and_secret_boundary() -> None:
    """显式 Mapper 保留 ID、时间、顺序和凭据，默认输出不泄露密码。"""

    camera = CameraBuilder().build(source_count=10)
    camera_row, source_rows = camera_to_rows(camera)
    restored = rows_to_camera(camera_row, source_rows)

    assert restored == camera
    assert restored.credentials.password.reveal() == "builder-camera-secret"
    assert "builder-camera-secret" not in repr(camera_row)
    assert "builder-camera-secret" not in repr(restored)


async def test_fake_uow_isolates_uncommitted_commit_and_rollback_snapshots() -> None:
    """未提交副本不可见，commit 后新 UoW 可见，rollback 后无残留。"""

    store = FakeCameraStore()
    camera = CameraBuilder().build(source_count=1)
    writer = FakeCameraUnitOfWork(store)
    await writer.cameras.add(camera)

    assert await FakeCameraUnitOfWork(store).cameras.get(camera.camera_id) is None
    await writer.commit()
    assert await FakeCameraUnitOfWork(store).cameras.get(camera.camera_id) == camera

    deleting = FakeCameraUnitOfWork(store)
    assert await deleting.cameras.delete(camera.camera_id) == camera
    await deleting.rollback()
    assert await deleting.cameras.get(camera.camera_id) == camera
    assert await FakeCameraUnitOfWork(store).cameras.get(camera.camera_id) == camera


async def test_fake_repository_save_delete_and_not_found_contract() -> None:
    """Fake 的完整集合 save 与 delete 返回值和生产端口一致。"""

    original, updated = _updated_camera_with_replacement_source()
    store = FakeCameraStore()
    uow = FakeCameraUnitOfWork(store)
    await uow.cameras.add(original)
    await uow.commit()

    updating = FakeCameraUnitOfWork(store)
    await updating.cameras.save(updated)
    await updating.commit()
    restored = await FakeCameraUnitOfWork(store).cameras.get(original.camera_id)
    assert restored == updated
    assert tuple(source.source_id for source in restored.sources) == (
        original.sources[1].source_id,
        uuid4_from_index(99),
    )

    deleting = FakeCameraUnitOfWork(store)
    assert await deleting.cameras.delete(original.camera_id) == updated
    assert await deleting.cameras.delete(uuid4_from_index(500)) is None


async def test_fake_repository_runs_shared_aggregate_contract() -> None:
    """Fake 与 PostgreSQL 实现必须执行同一组基础端口断言。"""

    original, updated = _updated_camera_with_replacement_source()
    uow = FakeCameraUnitOfWork(FakeCameraStore())
    await assert_camera_repository_contract(uow.cameras, original, updated)


async def test_fake_literal_search_fixed_sort_count_and_pagination() -> None:
    """ASCII/中文/IP 与 %、_、反斜杠都按字面包含匹配，并先过滤再分页。"""

    store = FakeCameraStore()
    uow = FakeCameraUnitOfWork(store)
    names = ("Alpha 中文", "literal %/_/\\ marker", "alpha second")
    for index, name in enumerate(names):
        builder = CameraBuilder()
        builder.name = name
        builder.ip_address = f"192.168.10.{index + 1}"
        await uow.cameras.add(builder.build(source_count=1, id_start=1 + index * 10))
    await uow.commit()

    reader = FakeCameraUnitOfWork(store).cameras
    assert await reader.count(CameraListCriteria(q="ALPHA")) == 2
    assert len(await reader.list(CameraListCriteria(q="中文"), 1, 100)) == 1
    assert len(await reader.list(CameraListCriteria(q="192.168.10.2"), 1, 100)) == 1
    for literal in ("%", "_", "\\"):
        found = await reader.list(CameraListCriteria(q=literal), 1, 100)
        assert tuple(camera.name for camera in found) == ("literal %/_/\\ marker",)

    first_page = await reader.list(CameraListCriteria(q="alpha"), 1, 1)
    second_page = await reader.list(CameraListCriteria(q="alpha"), 2, 1)
    assert first_page[0].camera_id < second_page[0].camera_id
    assert await reader.list(CameraListCriteria(q="alpha"), 3, 1) == ()

    pagination_store = FakeCameraStore()
    pagination_uow = FakeCameraUnitOfWork(pagination_store)
    pagination_cameras = CameraListBuilder().build(10)
    for camera in reversed(pagination_cameras):
        await pagination_uow.cameras.add(camera)
    await pagination_uow.commit()
    pagination_reader = FakeCameraUnitOfWork(pagination_store).cameras
    assert await pagination_reader.list(CameraListCriteria(), 2, 3) == pagination_cameras[3:6]
    assert await pagination_reader.count(CameraListCriteria()) == 10


class _Diagnostic:
    constraint_name = "uq_camera_sources_camera_id_url_suffix"


class _DriverError(Exception):
    diag = _Diagnostic()


class _InvalidDiagnostic:
    # 非字符串且不可哈希的值用于证明动态驱动边界不会让错误翻译器再次失败。
    constraint_name = ["invalid"]


class _InvalidDriverError(Exception):
    diag = _InvalidDiagnostic()


def test_integrity_translation_uses_only_structured_constraint_name() -> None:
    """已知约束转换为稳定 kind，未知约束不解析底层错误文本。"""

    known = IntegrityError("敏感 SQL", {"password": "secret"}, _DriverError("secret"))
    translated = translate_integrity_error(known)
    assert isinstance(translated, CameraConstraintViolationError)
    assert translated.kind is CameraConstraintViolationKind.DUPLICATE_SOURCE_SUFFIX
    assert "secret" not in str(translated)

    unknown = IntegrityError("敏感 SQL", {}, Exception("unknown secret"))
    safe_unknown = translate_integrity_error(unknown)
    assert isinstance(safe_unknown, CameraPersistenceOperationError)
    assert "secret" not in str(safe_unknown)

    invalid = IntegrityError("敏感 SQL", {}, _InvalidDriverError("invalid secret"))
    safe_invalid = translate_integrity_error(invalid)
    assert isinstance(safe_invalid, CameraPersistenceOperationError)
    assert "secret" not in str(safe_invalid)


async def test_sqlalchemy_uow_commit_failure_rolls_back_before_safe_error() -> None:
    """延迟约束在 commit 报错时，UoW 先恢复 Session 再暴露安全错误。"""

    session = AsyncMock(spec=AsyncSession)
    session.commit.side_effect = IntegrityError(
        "敏感 SQL",
        {"password": "secret"},
        _DriverError("secret"),
    )
    uow = SQLAlchemyCameraUnitOfWork(session)

    with pytest.raises(CameraConstraintViolationError) as captured:
        await uow.commit()
    session.rollback.assert_awaited_once()
    assert captured.value.kind is CameraConstraintViolationKind.DUPLICATE_SOURCE_SUFFIX


async def test_sqlalchemy_uow_cancellation_rolls_back_and_propagates() -> None:
    """任务取消不被包装为业务错误，且不会留下未清理事务。"""

    session = AsyncMock(spec=AsyncSession)
    session.commit.side_effect = asyncio.CancelledError
    uow = SQLAlchemyCameraUnitOfWork(session)

    with pytest.raises(asyncio.CancelledError):
        await uow.commit()
    session.rollback.assert_awaited_once()


def test_camera_uow_dependency_reuses_request_session() -> None:
    """API Composition Root 只装配当前请求 Session，不创建第二个事务资源。"""

    session = AsyncMock(spec=AsyncSession)

    uow = get_camera_unit_of_work(session)

    assert isinstance(uow, SQLAlchemyCameraUnitOfWork)
    assert uow._session is session
    assert uow.cameras._session is session
