"""Camera 持久化端口、Mapper、Fake 与错误转换的确定性单元测试。"""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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
from tests.support.cameras.builders import (
    FIXED_TIME,
    CameraBuilder,
    CameraListBuilder,
    FixedClock,
    FixedIdGenerator,
    uuid4_from_index,
)
from tests.support.cameras.constants import CAMERA_LEAK_SENTINEL
from tests.support.cameras.fakes import FakeCameraStore, FakeCameraUnitOfWork
from tests.support.cameras.repository_contract import assert_camera_repository_contract

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


def test_列表条件和分页拒绝未规范化的边界值() -> None:
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


@pytest.mark.sensitive_data
def test_映射器往返保留完整聚合与敏感信息边界() -> None:
    """显式 Mapper 保留 ID、时间、顺序和凭据，默认输出不泄露密码。"""

    camera = CameraBuilder().build(source_count=10)
    camera_row, source_rows = camera_to_rows(camera)
    restored = rows_to_camera(camera_row, source_rows)

    assert restored == camera
    assert restored.credentials.password.reveal() == CAMERA_LEAK_SENTINEL
    assert CAMERA_LEAK_SENTINEL not in repr(camera_row)
    assert CAMERA_LEAK_SENTINEL not in repr(restored)


async def test_假工作单元隔离未提交提交和回滚快照() -> None:
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


async def test_假仓储通过共享聚合检查() -> None:
    """Fake 与 PostgreSQL 实现必须执行同一组基础端口断言。"""

    original, updated = _updated_camera_with_replacement_source()
    uow = FakeCameraUnitOfWork(FakeCameraStore())
    await assert_camera_repository_contract(uow.cameras, original, updated)


async def test_假仓储按字面值搜索固定排序计数和分页() -> None:
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


def test_完整性错误转换只使用结构化约束名称() -> None:
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


async def test_SQLAlchemy工作单元提交失败时先回滚再返回安全错误() -> None:
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


async def test_SQLAlchemy工作单元取消时回滚并继续抛出() -> None:
    """任务取消不被包装为业务错误，且不会留下未清理事务。"""

    session = AsyncMock(spec=AsyncSession)
    session.commit.side_effect = asyncio.CancelledError
    uow = SQLAlchemyCameraUnitOfWork(session)

    with pytest.raises(asyncio.CancelledError):
        await uow.commit()
    session.rollback.assert_awaited_once()
