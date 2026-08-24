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

from app.modules.cameras.persistence.errors import (
    CameraNotFoundError,
    DefaultSourceReplacementRequiredError,
    InvalidCameraAggregateError,
    LastCameraSourceError,
    SourceNotOwnedByCameraError,
)
from app.modules.cameras.persistence.integrity import (
    ReferenceIntegrityIssueKind,
    scan_reference_integrity,
)
from app.modules.cameras.persistence.models import CameraRow, CameraSourceRow
from app.modules.cameras.persistence.repository import CameraPersistenceRepository
from tests.core.database.test_migrations import (
    BACKEND_ROOT,
    temporary_database,
    validate_test_database_url,
)

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


async def seed_two_source_camera(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """通过 Repository 写入一个双 Source Camera。"""

    async with factory() as session, session.begin():
        await CameraPersistenceRepository(session).add_aggregate(
            make_camera(CAMERA_A, SOURCE_A),
            (
                make_source(SOURCE_A, CAMERA_A, 0),
                make_source(SOURCE_B, CAMERA_A, 1),
            ),
        )


async def row_counts(factory: async_sessionmaker[AsyncSession]) -> tuple[int, int]:
    """读取 Camera 与 Source 记录数。"""

    async with factory() as session:
        camera_count = await session.scalar(select(func.count()).select_from(CameraRow))
        source_count = await session.scalar(select(func.count()).select_from(CameraSourceRow))
    assert camera_count is not None
    assert source_count is not None
    return camera_count, source_count


async def test_add_and_explicit_delete_are_atomic(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """显式删除聚合支持完整回滚，成功后不残留 Source。"""

    await seed_two_source_camera(session_factory)

    with pytest.raises(RuntimeError, match="模拟业务失败"):
        async with session_factory() as session, session.begin():
            await CameraPersistenceRepository(session).delete_camera(CAMERA_A)
            raise RuntimeError("模拟业务失败")

    assert await row_counts(session_factory) == (1, 2)

    async with session_factory() as session, session.begin():
        await CameraPersistenceRepository(session).delete_camera(CAMERA_A)

    assert await row_counts(session_factory) == (0, 0)


async def test_repository_rejects_invalid_logical_references(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """不存在父项、跨 Camera 默认源和危险 Source 删除均被事务边界拒绝。"""

    await seed_two_source_camera(session_factory)
    async with session_factory() as session, session.begin():
        with pytest.raises(InvalidCameraAggregateError):
            await CameraPersistenceRepository(session).add_aggregate(
                make_camera(CAMERA_B, SOURCE_MISSING),
                (make_source(SOURCE_C, CAMERA_B, 0),),
            )

    async with session_factory() as session, session.begin():
        with pytest.raises(CameraNotFoundError):
            await CameraPersistenceRepository(session).add_source(
                make_source(SOURCE_C, CAMERA_B, 0)
            )

    async with session_factory() as session, session.begin():
        session.add(make_camera(CAMERA_B, SOURCE_C))
        session.add(make_source(SOURCE_C, CAMERA_B, 0))

    async with session_factory() as session, session.begin():
        with pytest.raises(SourceNotOwnedByCameraError):
            await CameraPersistenceRepository(session).set_default_source(CAMERA_A, SOURCE_C)

    async with session_factory() as session, session.begin():
        with pytest.raises(DefaultSourceReplacementRequiredError):
            await CameraPersistenceRepository(session).delete_source(CAMERA_A, SOURCE_A)

    async with session_factory() as session, session.begin():
        await CameraPersistenceRepository(session).delete_source(
            CAMERA_A,
            SOURCE_A,
            replacement_default_source_id=SOURCE_B,
        )

    async with session_factory() as session, session.begin():
        with pytest.raises(LastCameraSourceError):
            await CameraPersistenceRepository(session).delete_source(CAMERA_A, SOURCE_B)


async def test_source_add_waits_for_camera_delete_and_cannot_create_orphan(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Camera 行锁让新增 Source 在并发删除提交后失败。"""

    await seed_two_source_camera(session_factory)

    async def add_source() -> None:
        async with session_factory() as session, session.begin():
            await CameraPersistenceRepository(session).add_source(
                make_source(SOURCE_C, CAMERA_A, 2)
            )

    async with session_factory() as deleting_session:
        async with deleting_session.begin():
            await CameraPersistenceRepository(deleting_session).delete_camera(CAMERA_A)
            add_task = asyncio.create_task(add_source())
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(add_task), timeout=0.1)

    with pytest.raises(CameraNotFoundError):
        await asyncio.wait_for(add_task, timeout=3)
    assert await row_counts(session_factory) == (0, 0)


async def test_default_update_serializes_with_source_delete(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """默认源切换提交后，并发删除会重新检查最新默认源。"""

    await seed_two_source_camera(session_factory)

    async def delete_new_default() -> None:
        async with session_factory() as session, session.begin():
            await CameraPersistenceRepository(session).delete_source(CAMERA_A, SOURCE_B)

    async with session_factory() as updating_session:
        async with updating_session.begin():
            await CameraPersistenceRepository(updating_session).set_default_source(
                CAMERA_A,
                SOURCE_B,
            )
            delete_task = asyncio.create_task(delete_new_default())
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(delete_task), timeout=0.1)

    with pytest.raises(DefaultSourceReplacementRequiredError):
        await asyncio.wait_for(delete_task, timeout=3)

    async with session_factory() as session:
        camera = await session.get(CameraRow, CAMERA_A)
        source = await session.get(CameraSourceRow, SOURCE_B)
    assert camera is not None
    assert camera.default_preview_source_id == SOURCE_B
    assert source is not None


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
            await CameraPersistenceRepository(session).add_aggregate(
                make_camera(CAMERA_A, SOURCE_A),
                (
                    make_source(SOURCE_A, CAMERA_A, 0, url_suffix="same"),
                    make_source(SOURCE_B, CAMERA_A, 1, url_suffix="same"),
                ),
            )

    with pytest.raises(IntegrityError):
        async with session_factory() as session, session.begin():
            await CameraPersistenceRepository(session).add_aggregate(
                make_camera(CAMERA_A, SOURCE_A),
                (
                    make_source(SOURCE_A, CAMERA_A, 0),
                    make_source(SOURCE_B, CAMERA_A, 0),
                ),
            )


async def test_primary_keys_reject_duplicate_camera_and_source_ids(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Camera 与 Source UUID 主键都保持全局唯一。"""

    await seed_two_source_camera(session_factory)

    with pytest.raises(IntegrityError):
        async with session_factory() as session, session.begin():
            await CameraPersistenceRepository(session).add_aggregate(
                make_camera(CAMERA_A, SOURCE_C),
                (make_source(SOURCE_C, CAMERA_A, 0),),
            )

    with pytest.raises(IntegrityError):
        async with session_factory() as session, session.begin():
            await CameraPersistenceRepository(session).add_aggregate(
                make_camera(CAMERA_B, SOURCE_A),
                (make_source(SOURCE_A, CAMERA_B, 0),),
            )


async def test_suffix_uniqueness_is_scoped_and_case_sensitive(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """同 Camera 的大小写不同后缀和不同 Camera 的相同后缀都可提交。"""

    async with session_factory() as session, session.begin():
        repository = CameraPersistenceRepository(session)
        await repository.add_aggregate(
            make_camera(CAMERA_A, SOURCE_A),
            (
                make_source(SOURCE_A, CAMERA_A, 0, url_suffix="ABC"),
                make_source(SOURCE_B, CAMERA_A, 1, url_suffix="abc"),
            ),
        )
        await repository.add_aggregate(
            make_camera(CAMERA_B, SOURCE_C),
            (make_source(SOURCE_C, CAMERA_B, 0, url_suffix="ABC"),),
        )

    assert await row_counts(session_factory) == (2, 3)


async def test_deferred_uniques_allow_source_suffix_and_order_swaps(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """事务内交换后缀和顺序不会被中间重复状态提前拒绝。"""

    await seed_two_source_camera(session_factory)
    async with session_factory() as session, session.begin():
        repository = CameraPersistenceRepository(session)
        first = await repository.get_source_for_update(CAMERA_A, SOURCE_A)
        second = await repository.get_source_for_update(CAMERA_A, SOURCE_B)
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
