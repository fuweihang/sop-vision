"""Camera 无外键 Repository 的真实 PostgreSQL 事务与并发验收。"""

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from ipaddress import IPv4Address, IPv6Address
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, func, select
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.modules.cameras.application import (
    CameraConstraintViolationError,
    CameraConstraintViolationKind,
    CameraListCriteria,
    CameraNotFoundError,
)
from app.modules.cameras.domain import (
    CameraAggregateCorruptedError,
    CameraSourceChange,
)
from app.modules.cameras.persistence.integrity import (
    ReferenceIntegrityIssueKind,
    scan_reference_integrity,
)
from app.modules.cameras.persistence.models import CameraRow, CameraSourceRow
from app.modules.cameras.persistence.repository import SQLAlchemyCameraRepository
from app.modules.cameras.persistence.uow import SQLAlchemyCameraUnitOfWork
from tests.core.database.test_migrations import (
    BACKEND_ROOT,
    temporary_database,
    validate_test_database_url,
)
from tests.modules.cameras.builders import (
    CameraBuilder,
    FixedClock,
    FixedIdGenerator,
    uuid4_from_index,
)
from tests.modules.cameras.repository_contract import assert_camera_repository_contract

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 8, 24, 8, 0, tzinfo=UTC)
CAMERA_A = UUID("00000000-0000-4000-8000-000000000001")
CAMERA_B = UUID("00000000-0000-4000-8000-000000000002")
CAMERA_C = UUID("00000000-0000-4000-8000-000000000003")
CAMERA_D = UUID("00000000-0000-4000-8000-000000000004")
ORPHAN_CAMERA = UUID("00000000-0000-4000-8000-000000000099")
SOURCE_A = UUID("10000000-0000-4000-8000-000000000001")
SOURCE_B = UUID("10000000-0000-4000-8000-000000000002")
SOURCE_C = UUID("10000000-0000-4000-8000-000000000003")
SOURCE_ORPHAN = UUID("10000000-0000-4000-8000-000000000099")
SOURCE_MISSING = UUID("20000000-0000-4000-8000-000000000099")


def make_camera(
    camera_id: UUID,
    default_source_id: UUID,
    *,
    rtsp_port: int = 554,
) -> CameraRow:
    """构造不在 repr 中输出密码的 ORM 测试记录。"""

    return CameraRow(
        camera_id=camera_id,
        name=f"Camera {camera_id}",
        ip_address=IPv4Address("192.0.2.10"),
        rtsp_port=rtsp_port,
        username="operator",
        password="repository-test-password",
        default_preview_source_id=default_source_id,
        created_at=NOW,
        updated_at=NOW,
    )


def make_source(
    source_id: UUID,
    camera_id: UUID,
    sort_order: int,
    *,
    url_suffix: str | None = None,
) -> CameraSourceRow:
    """构造具有确定 ID、顺序和后缀的 Source 记录。"""

    return CameraSourceRow(
        source_id=source_id,
        camera_id=camera_id,
        name=f"Source {sort_order}",
        url_suffix=url_suffix or f"stream/{source_id}",
        sort_order=sort_order,
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.fixture(scope="module")
def migrated_database_url() -> Iterator[URL]:
    """为 Repository 测试创建独占数据库并升级到最新 revision。"""

    raw_test_url = os.getenv("TEST_DATABASE_URL")
    if raw_test_url is None:
        pytest.skip("未配置 TEST_DATABASE_URL")
    raw_application_url = os.getenv("DATABASE_URL")
    if raw_application_url is None:
        pytest.fail("验证测试数据库隔离性需要配置 DATABASE_URL")

    configured_url = validate_test_database_url(raw_test_url, raw_application_url)
    assert configured_url.database is not None
    database_stem = configured_url.database.removesuffix("_test")
    repository_url = configured_url.set(database=f"{database_stem}_repository_test")

    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    alembic_config.attributes["database_url"] = repository_url.render_as_string(hide_password=False)
    with temporary_database(repository_url):
        command.upgrade(alembic_config, "head")
        yield repository_url


@pytest.fixture
async def session_factory(
    migrated_database_url: URL,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """每例清空数据，但复用已迁移的独占数据库。"""

    engine = create_async_engine(
        migrated_database_url,
        hide_parameters=True,
        pool_pre_ping=True,
    )
    factory = async_sessionmaker(engine, autoflush=False, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(delete(CameraSourceRow))
        await connection.execute(delete(CameraRow))
    try:
        yield factory
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(CameraSourceRow))
            await connection.execute(delete(CameraRow))
        await engine.dispose()


async def row_counts(factory: async_sessionmaker[AsyncSession]) -> tuple[int, int]:
    """读取 Camera 与 Source 记录数。"""

    async with factory() as session:
        camera_count = await session.scalar(select(func.count()).select_from(CameraRow))
        source_count = await session.scalar(select(func.count()).select_from(CameraSourceRow))
    assert camera_count is not None
    assert source_count is not None
    return camera_count, source_count


async def test_postgresql_single_table_constraints_remain_enforced(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """无外键不影响端口、排序和同 Camera 后缀唯一约束。"""

    with pytest.raises(IntegrityError):
        async with session_factory() as session, session.begin():
            session.add(make_camera(CAMERA_A, SOURCE_A, rtsp_port=0))

    with pytest.raises(IntegrityError):
        async with session_factory() as session, session.begin():
            camera = make_camera(CAMERA_A, SOURCE_A)
            camera.ip_address = IPv6Address("2001:db8::10")  # type: ignore[assignment]
            session.add(camera)

    with pytest.raises(IntegrityError):
        async with session_factory() as session, session.begin():
            session.add(make_source(SOURCE_A, ORPHAN_CAMERA, -1))

    with pytest.raises(IntegrityError):
        async with session_factory() as session, session.begin():
            session.add_all(
                (
                    make_camera(CAMERA_A, SOURCE_A),
                    make_source(SOURCE_A, CAMERA_A, 0, url_suffix="same"),
                    make_source(SOURCE_B, CAMERA_A, 1, url_suffix="same"),
                )
            )

    with pytest.raises(IntegrityError):
        async with session_factory() as session, session.begin():
            session.add_all(
                (
                    make_camera(CAMERA_A, SOURCE_A),
                    make_source(SOURCE_A, CAMERA_A, 0),
                    make_source(SOURCE_B, CAMERA_A, 0),
                )
            )


async def test_primary_keys_reject_duplicate_camera_and_source_ids(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Camera 与 Source UUID 主键都保持全局唯一。"""

    async with session_factory() as session, session.begin():
        session.add_all(
            (
                make_camera(CAMERA_A, SOURCE_A),
                make_source(SOURCE_A, CAMERA_A, 0),
                make_source(SOURCE_B, CAMERA_A, 1),
            )
        )

    with pytest.raises(IntegrityError):
        async with session_factory() as session, session.begin():
            session.add(make_camera(CAMERA_A, SOURCE_C))

    with pytest.raises(IntegrityError):
        async with session_factory() as session, session.begin():
            session.add(make_source(SOURCE_A, CAMERA_B, 0))


async def test_suffix_uniqueness_is_scoped_and_case_sensitive(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """同 Camera 的大小写不同后缀和不同 Camera 的相同后缀都可提交。"""

    async with session_factory() as session, session.begin():
        session.add_all(
            (
                make_camera(CAMERA_A, SOURCE_A),
                make_source(SOURCE_A, CAMERA_A, 0, url_suffix="ABC"),
                make_source(SOURCE_B, CAMERA_A, 1, url_suffix="abc"),
                make_camera(CAMERA_B, SOURCE_C),
                make_source(SOURCE_C, CAMERA_B, 0, url_suffix="ABC"),
            )
        )

    assert await row_counts(session_factory) == (2, 3)


async def test_deferred_uniques_allow_source_suffix_and_order_swaps(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """事务内交换后缀和顺序不会被中间重复状态提前拒绝。"""

    async with session_factory() as session, session.begin():
        session.add_all(
            (
                make_camera(CAMERA_A, SOURCE_A),
                make_source(SOURCE_A, CAMERA_A, 0),
                make_source(SOURCE_B, CAMERA_A, 1),
            )
        )

    async with session_factory() as session, session.begin():
        rows = tuple(
            (
                await session.scalars(
                    select(CameraSourceRow)
                    .where(CameraSourceRow.camera_id == CAMERA_A)
                    .order_by(CameraSourceRow.source_id)
                    .with_for_update()
                )
            ).all()
        )
        first, second = rows
        first.sort_order, second.sort_order = second.sort_order, first.sort_order
        first.url_suffix, second.url_suffix = second.url_suffix, first.url_suffix
        await session.flush()

    async with session_factory() as session:
        rows = (
            await session.scalars(
                select(CameraSourceRow)
                .where(CameraSourceRow.camera_id == CAMERA_A)
                .order_by(CameraSourceRow.sort_order)
            )
        ).all()
    assert [row.source_id for row in rows] == [SOURCE_B, SOURCE_A]


async def test_integrity_scan_detects_all_cross_table_anomalies(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """直接 SQL/ORM 绕过 Repository 后，巡检只读识别四类异常。"""

    async with session_factory() as session, session.begin():
        session.add_all(
            (
                make_camera(CAMERA_A, SOURCE_A),
                make_source(SOURCE_A, CAMERA_A, 0),
                make_camera(CAMERA_B, SOURCE_MISSING),
                make_source(SOURCE_B, CAMERA_B, 0),
                make_camera(CAMERA_C, SOURCE_A),
                make_source(SOURCE_C, CAMERA_C, 0),
                make_camera(CAMERA_D, SOURCE_MISSING),
                make_source(SOURCE_ORPHAN, ORPHAN_CAMERA, 0),
            )
        )

    async with session_factory() as session:
        issues = await scan_reference_integrity(session)

    assert {issue.kind for issue in issues} == {
        ReferenceIntegrityIssueKind.ORPHAN_SOURCE,
        ReferenceIntegrityIssueKind.MISSING_DEFAULT_SOURCE,
        ReferenceIntegrityIssueKind.DEFAULT_SOURCE_OWNED_BY_ANOTHER_CAMERA,
        ReferenceIntegrityIssueKind.CAMERA_WITHOUT_SOURCE,
    }
    assert await row_counts(session_factory) == (4, 4)


async def test_camera_repository_round_trip_literal_search_and_transaction_visibility(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """聚合端口一次读全 Source，且未提交写入对其他事务不可见。"""

    camera_builder = CameraBuilder()
    camera_builder.name = "Alpha 中文 %/_/\\ Camera"
    camera_builder.ip_address = "192.168.10.21"
    camera = camera_builder.build(source_count=10, id_start=100)

    async with session_factory() as writing_session:
        uow = SQLAlchemyCameraUnitOfWork(writing_session)
        await uow.cameras.add(camera)
        async with session_factory() as other_session:
            other_repository = SQLAlchemyCameraRepository(other_session)
            assert await other_repository.get(camera.camera_id) is None
        await uow.commit()

    async with session_factory() as reading_session:
        repository = SQLAlchemyCameraRepository(reading_session)
        restored = await repository.get(camera.camera_id)
        assert restored == camera
        assert restored.credentials.password.reveal() == "builder-camera-secret"
        assert await repository.count(CameraListCriteria(q="ALPHA")) == 1
        assert await repository.count(CameraListCriteria(q="中文")) == 1
        assert await repository.count(CameraListCriteria(q="192.168.10.21")) == 1
        for literal in ("%", "_", "\\"):
            assert await repository.list(CameraListCriteria(q=literal), 1, 100) == (camera,)
        assert await repository.list(CameraListCriteria(), 2, 100) == ()


async def test_sqlalchemy_repository_runs_shared_aggregate_contract(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """真实 PostgreSQL 与 Fake 执行完全相同的基础聚合端口断言。"""

    camera = CameraBuilder().build(source_count=2, id_start=500)
    retained = camera.sources[1]
    updated = camera.update_configuration(
        name="共享契约更新",
        ip_address=camera.ip_address,
        rtsp_port=camera.rtsp_port,
        username=camera.credentials.username,
        password=camera.credentials.password.reveal(),
        sources=(
            CameraSourceChange(
                source_id=retained.source_id,
                name=retained.name,
                url_suffix=retained.url_suffix,
                is_default_preview=True,
            ),
            CameraSourceChange(name="共享契约新增", url_suffix="contract-new"),
        ),
        id_generator=FixedIdGenerator((uuid4_from_index(599),)),
        clock=FixedClock(NOW.replace(microsecond=1)),
    )
    async with session_factory() as session:
        uow = SQLAlchemyCameraUnitOfWork(session)
        await assert_camera_repository_contract(uow.cameras, camera, updated)
        await uow.rollback()


async def test_camera_repository_save_swap_and_delete_rollback_are_atomic(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """完整更新可安全交换延迟唯一字段，并显式增删 Source。"""

    camera = CameraBuilder().build(source_count=2, id_start=200)
    async with session_factory() as session:
        uow = SQLAlchemyCameraUnitOfWork(session)
        await uow.cameras.add(camera)
        await uow.commit()

    first, second = camera.sources
    updated = camera.update_configuration(
        name="更新后的 Camera",
        ip_address=camera.ip_address,
        rtsp_port=camera.rtsp_port,
        username=camera.credentials.username,
        password=camera.credentials.password.reveal(),
        sources=(
            CameraSourceChange(
                source_id=second.source_id,
                name=second.name,
                url_suffix=first.url_suffix,
                is_default_preview=True,
            ),
            CameraSourceChange(
                name="新增 Source",
                url_suffix=second.url_suffix,
            ),
        ),
        id_generator=FixedIdGenerator((uuid4_from_index(299),)),
        clock=FixedClock(NOW.replace(microsecond=1)),
    )
    async with session_factory() as session:
        uow = SQLAlchemyCameraUnitOfWork(session)
        await uow.cameras.save(updated)
        await uow.commit()

    async with session_factory() as session:
        uow = SQLAlchemyCameraUnitOfWork(session)
        assert await uow.cameras.get(camera.camera_id) == updated
        assert await uow.cameras.delete(camera.camera_id) == updated
        await uow.rollback()

    async with session_factory() as session:
        uow = SQLAlchemyCameraUnitOfWork(session)
        assert await uow.cameras.get(camera.camera_id) == updated
        assert await uow.cameras.delete(camera.camera_id) == updated
        await uow.commit()
    async with session_factory() as session:
        assert await SQLAlchemyCameraRepository(session).get(camera.camera_id) is None


async def test_uow_converts_deferred_constraint_at_commit_and_restores_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """延迟后缀冲突只在 commit 报错，并转换为不含底层细节的稳定 kind。"""

    camera = CameraBuilder().build(source_count=2, id_start=300)
    async with session_factory() as session:
        uow = SQLAlchemyCameraUnitOfWork(session)
        await uow.cameras.add(camera)
        await uow.commit()

    async with session_factory() as session:
        uow = SQLAlchemyCameraUnitOfWork(session)
        rows = tuple(
            (
                await session.scalars(
                    select(CameraSourceRow)
                    .where(CameraSourceRow.camera_id == camera.camera_id)
                    .order_by(CameraSourceRow.sort_order)
                )
            ).all()
        )
        rows[1].url_suffix = rows[0].url_suffix
        await session.flush()
        with pytest.raises(CameraConstraintViolationError) as captured:
            await uow.commit()
        assert captured.value.kind is CameraConstraintViolationKind.DUPLICATE_SOURCE_SUFFIX
        assert "builder-camera-secret" not in str(captured.value)

        # commit 失败路径已 rollback，同一个 Session 可以继续安全读取原值。
        restored = await uow.cameras.get(camera.camera_id)
        assert restored == camera


async def test_camera_repository_rejects_corrupted_rows_instead_of_partial_camera(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """直接绕过 Repository 写出的无 Source Camera 无法伪装成合法聚合。"""

    async with session_factory() as session:
        session.add(make_camera(CAMERA_A, SOURCE_A))
        await session.commit()

    async with session_factory() as session:
        repository = SQLAlchemyCameraRepository(session)
        with pytest.raises(CameraAggregateCorruptedError):
            await repository.get(CAMERA_A)


async def test_aggregate_get_for_update_serializes_same_camera_intent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """聚合端口的 ``for_update`` 会串行化同一 Camera 的并发写意图。"""

    camera = CameraBuilder().build(source_count=2, id_start=400)
    async with session_factory() as session:
        uow = SQLAlchemyCameraUnitOfWork(session)
        await uow.cameras.add(camera)
        await uow.commit()

    async def acquire_same_aggregate() -> None:
        async with session_factory() as session:
            repository = SQLAlchemyCameraRepository(session)
            assert await repository.get(camera.camera_id, for_update=True) == camera

    async with session_factory() as locking_session:
        repository = SQLAlchemyCameraRepository(locking_session)
        assert await repository.get(camera.camera_id, for_update=True) == camera
        waiting_task = asyncio.create_task(acquire_same_aggregate())
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(waiting_task), timeout=0.1)
        await locking_session.rollback()

    await asyncio.wait_for(waiting_task, timeout=3)


async def test_camera_delete_serializes_concurrent_save_without_orphan_sources(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """删除提交前并发 save 必须等待，随后按最新数据库事实报告 Camera 不存在。"""

    camera = CameraBuilder().build(source_count=2, id_start=600)
    updated = camera.change_default_preview_source(
        camera.sources[1].source_id,
        clock=FixedClock(NOW.replace(microsecond=1)),
    )
    async with session_factory() as session:
        uow = SQLAlchemyCameraUnitOfWork(session)
        await uow.cameras.add(camera)
        await uow.commit()

    save_started = asyncio.Event()

    async def save_after_delete() -> None:
        async with session_factory() as session:
            uow = SQLAlchemyCameraUnitOfWork(session)
            save_started.set()
            with pytest.raises(CameraNotFoundError):
                await uow.cameras.save(updated)
            await uow.rollback()

    async with session_factory() as deleting_session:
        deleting_uow = SQLAlchemyCameraUnitOfWork(deleting_session)
        assert await deleting_uow.cameras.delete(camera.camera_id) == camera

        waiting_save = asyncio.create_task(save_after_delete())
        await asyncio.wait_for(save_started.wait(), timeout=1)
        # save 与 delete 使用相同的 Camera → Source 锁顺序，因此删除提交前不能继续。
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(waiting_save), timeout=0.1)
        await deleting_uow.commit()

    await asyncio.wait_for(waiting_save, timeout=3)
    assert await row_counts(session_factory) == (0, 0)
