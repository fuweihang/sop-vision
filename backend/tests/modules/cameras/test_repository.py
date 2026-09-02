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

from app.modules.cameras.api.mappers import camera_detail_from_runtime
from app.modules.cameras.application import (
    CameraAggregateInvalidError,
    CameraConstraintViolationError,
    CameraConstraintViolationKind,
    CameraListAggregateInvalidError,
    CameraListCriteria,
    CameraNotFoundError,
    CreateCameraCommand,
    CreateCameraSourceCommand,
    SetDefaultPreviewSourceCommand,
    UpdateCameraCommand,
    UpdateCameraSourceCommand,
    create_camera,
    get_camera_detail,
    list_cameras,
    set_default_preview_source,
    update_camera,
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
from app.modules.stream_gateway.ports import RuntimePath, RuntimePathSnapshot
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
from tests.modules.cameras.constants import CAMERA_LEAK_SENTINEL
from tests.modules.cameras.fakes import FakeStreamGateway
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
        assert restored.credentials.password.reveal() == CAMERA_LEAK_SENTINEL
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
        assert CAMERA_LEAK_SENTINEL not in str(captured.value)

        # commit 失败路径已 rollback，同一个 Session 可以继续安全读取原值。
        restored = await uow.cameras.get(camera.camera_id)
        assert restored == camera


async def test_create_use_case_rolls_back_flush_collision_before_media(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """真实 PostgreSQL 主键冲突在 add/flush 失败，创建用例回滚且零媒体调用。"""

    existing = CameraBuilder().build(source_count=1, id_start=350)
    async with session_factory() as session:
        existing_uow = SQLAlchemyCameraUnitOfWork(session)
        await existing_uow.cameras.add(existing)
        await existing_uow.commit()

    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=NOW))
    command = CreateCameraCommand(
        name="主键冲突 Camera",
        ip_address="192.0.2.80",
        rtsp_port=554,
        username="operator",
        password=CAMERA_LEAK_SENTINEL,
        sources=(
            CreateCameraSourceCommand(
                name="主码流",
                url_suffix="Streaming/Channels/101",
                is_default_preview=True,
            ),
        ),
    )
    async with session_factory() as session:
        failing_uow = SQLAlchemyCameraUnitOfWork(session)
        with pytest.raises(CameraConstraintViolationError) as captured:
            await create_camera(
                command,
                uow=failing_uow,
                stream_gateway=gateway,
                id_generator=FixedIdGenerator((existing.camera_id, uuid4_from_index(359))),
                clock=FixedClock(NOW),
            )

    assert captured.value.kind is CameraConstraintViolationKind.CAMERA_ID_ALREADY_EXISTS
    assert gateway.ensure_calls == []
    assert gateway.runtime_snapshot_count == 0
    assert await row_counts(session_factory) == (1, 1)
    async with session_factory() as session:
        assert await SQLAlchemyCameraRepository(session).get(existing.camera_id) == existing


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


async def test_camera_detail_reads_ordered_postgresql_aggregate_and_maps_complete_response(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """真实详情读取保持 Source 顺序、默认源、计数和按配置派生的 RTSP URL。"""

    camera = CameraBuilder().build(source_count=2, id_start=800)
    async with session_factory() as writing_session:
        writing_uow = SQLAlchemyCameraUnitOfWork(writing_session)
        await writing_uow.cameras.add(camera)
        await writing_uow.commit()

    default_source = camera.sources[0]
    gateway = FakeStreamGateway(
        RuntimePathSnapshot(
            paths=(RuntimePath(name=str(default_source.source_id), available=True, online=True),),
            checked_at=NOW,
        )
    )
    async with session_factory() as reading_session:
        result = await get_camera_detail(
            camera.camera_id,
            uow=SQLAlchemyCameraUnitOfWork(reading_session),
            stream_gateway=gateway,
            clock=FixedClock(NOW),
        )
        # Application 已在网络调用前显式 rollback；返回后不应留下只读事务。
        assert not reading_session.in_transaction()

    detail = camera_detail_from_runtime(
        result.camera,
        result.source_runtime,
        result.runtime_summary,
    )
    assert tuple(source.source_id for source in result.camera.sources) == tuple(
        source.source_id for source in camera.sources
    )
    assert detail.default_preview_source_id == default_source.source_id
    assert detail.online_source_count == 1
    assert detail.source_count == 2
    assert tuple(source.source_id for source in detail.sources) == tuple(
        source.source_id for source in camera.sources
    )
    assert tuple(source.rtsp_url for source in detail.sources) == tuple(
        camera.rtsp_url_for(source.source_id) for source in camera.sources
    )
    assert gateway.runtime_snapshot_count == 1
    assert gateway.ensure_calls == []


async def test_camera_detail_converts_postgresql_corruption_and_ends_read_transaction(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """真实 Repository 重建失败转换成安全详情错误，并在返回 500 前结束事务。"""

    async with session_factory() as writing_session:
        writing_session.add(make_camera(CAMERA_A, SOURCE_A))
        await writing_session.commit()

    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=NOW))
    async with session_factory() as reading_session:
        with pytest.raises(CameraAggregateInvalidError) as captured:
            await get_camera_detail(
                CAMERA_A,
                uow=SQLAlchemyCameraUnitOfWork(reading_session),
                stream_gateway=gateway,
                clock=FixedClock(NOW),
            )
        assert not reading_session.in_transaction()

    assert captured.value.camera_id == CAMERA_A
    assert captured.value.__context__ is None
    assert gateway.runtime_snapshot_count == 0
    assert gateway.ensure_calls == []


async def test_camera_list_reads_postgresql_page_after_ending_read_transaction(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """真实列表在事务外读取一次媒体快照，并保留 PostgreSQL 固定排序和分页总数。"""

    first = CameraBuilder().build(source_count=2, id_start=900)
    second = CameraBuilder().build(source_count=1, id_start=950)
    async with session_factory() as writing_session:
        writing_uow = SQLAlchemyCameraUnitOfWork(writing_session)
        await writing_uow.cameras.add(first)
        await writing_uow.cameras.add(second)
        await writing_uow.commit()

    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=NOW))
    async with session_factory() as reading_session:
        original_fetch = gateway.fetch_runtime_path_snapshot

        async def fetch_after_transaction() -> RuntimePathSnapshot:
            # 外部 I/O 开始前必须释放 PostgreSQL 事务，否则慢 MediaMTX 请求会占用数据库连接。
            assert not reading_session.in_transaction()
            return await original_fetch()

        gateway.fetch_runtime_path_snapshot = fetch_after_transaction  # type: ignore[method-assign]
        result = await list_cameras(
            CameraListCriteria(),
            1,
            1,
            uow=SQLAlchemyCameraUnitOfWork(reading_session),
            stream_gateway=gateway,
            clock=FixedClock(NOW),
        )
        assert not reading_session.in_transaction()

    assert result.total == 2
    assert tuple(item.camera.camera_id for item in result.items) == (first.camera_id,)
    assert gateway.runtime_snapshot_count == 1
    assert gateway.ensure_calls == []


async def test_camera_list_converts_postgresql_corruption_without_media_access(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """真实批量重建失败返回无 Camera 身份的列表错误，并先结束只读事务。"""

    async with session_factory() as writing_session:
        writing_session.add(make_camera(CAMERA_A, SOURCE_A))
        await writing_session.commit()

    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=NOW))
    async with session_factory() as reading_session:
        with pytest.raises(CameraListAggregateInvalidError) as captured:
            await list_cameras(
                CameraListCriteria(),
                1,
                20,
                uow=SQLAlchemyCameraUnitOfWork(reading_session),
                stream_gateway=gateway,
                clock=FixedClock(NOW),
            )
        assert not reading_session.in_transaction()

    assert not hasattr(captured.value, "camera_id")
    assert captured.value.__context__ is None
    assert gateway.runtime_snapshot_count == 0
    assert gateway.ensure_calls == []


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
            with pytest.raises(CameraNotFoundError) as captured:
                await uow.cameras.save(updated)
            assert captured.value.camera_id == camera.camera_id
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


async def test_camera_update_use_case_persists_complete_aggregate_before_media(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """真实 PostgreSQL 完整保存增删改排，且 MediaMTX I/O 开始前事务已经提交。"""

    camera = CameraBuilder().build(source_count=3, id_start=1_100)
    async with session_factory() as writing_session:
        writer = SQLAlchemyCameraUnitOfWork(writing_session)
        await writer.cameras.add(camera)
        await writer.commit()

    retained = camera.sources[1]
    new_source_id = uuid4_from_index(1_199)
    command = UpdateCameraCommand(
        camera_id=camera.camera_id,
        name="PostgreSQL 更新结果",
        ip_address="192.0.2.88",
        rtsp_port=8554,
        username="updated-operator",
        password=CAMERA_LEAK_SENTINEL,
        sources=(
            UpdateCameraSourceCommand(
                source_id=retained.source_id,
                name="保留 Source",
                url_suffix="changed/stream",
                is_default_preview=True,
            ),
            UpdateCameraSourceCommand(
                name="新增 Source",
                url_suffix="new/stream",
                is_default_preview=False,
            ),
        ),
    )
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=NOW))

    async with session_factory() as update_session:
        original_ensure = gateway.ensure_path

        async def ensure_after_commit(desired_source) -> None:
            # 外部调用不能继续占用 Camera 行锁或数据库连接事务。
            assert not update_session.in_transaction()
            await original_ensure(desired_source)

        gateway.ensure_path = ensure_after_commit  # type: ignore[method-assign]
        result = await update_camera(
            command,
            uow=SQLAlchemyCameraUnitOfWork(update_session),
            stream_gateway=gateway,
            id_generator=FixedIdGenerator((new_source_id,)),
            clock=FixedClock(NOW.replace(microsecond=1)),
        )
        assert not update_session.in_transaction()

    assert tuple(source.source_id for source in result.camera.sources) == (
        retained.source_id,
        new_source_id,
    )
    assert tuple(item.source_id for item in gateway.ensure_calls) == (
        retained.source_id,
        new_source_id,
    )
    assert gateway.release_calls == [camera.sources[0].source_id, camera.sources[2].source_id]
    async with session_factory() as reading_session:
        persisted = await SQLAlchemyCameraRepository(reading_session).get(camera.camera_id)
    assert persisted == result.camera
    assert await row_counts(session_factory) == (1, 2)


async def test_default_preview_source_use_case_only_persists_default_id_and_camera_time(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """真实 PostgreSQL 保存默认 ID 与 Camera 时间，Source 行内容和顺序完全不变。"""

    camera = CameraBuilder().build(source_count=2, id_start=1_250)
    async with session_factory() as writing_session:
        writer = SQLAlchemyCameraUnitOfWork(writing_session)
        await writer.cameras.add(camera)
        await writer.commit()

    async with session_factory() as reading_session:
        source_rows_before = tuple(
            (
                row.source_id,
                row.camera_id,
                row.name,
                row.url_suffix,
                row.sort_order,
                row.created_at,
                row.updated_at,
            )
            for row in (
                await reading_session.scalars(
                    select(CameraSourceRow)
                    .where(CameraSourceRow.camera_id == camera.camera_id)
                    .order_by(CameraSourceRow.sort_order.asc())
                )
            ).all()
        )

    changed_at = NOW.replace(microsecond=1)
    async with session_factory() as update_session:
        result = await set_default_preview_source(
            SetDefaultPreviewSourceCommand(
                camera_id=camera.camera_id,
                source_id=camera.sources[1].source_id,
            ),
            uow=SQLAlchemyCameraUnitOfWork(update_session),
            clock=FixedClock(changed_at),
        )
        assert not update_session.in_transaction()

    assert result.default_preview_source_id == camera.sources[1].source_id
    assert result.updated_at == changed_at
    async with session_factory() as reading_session:
        persisted = await SQLAlchemyCameraRepository(reading_session).get(camera.camera_id)
        source_rows_after = tuple(
            (
                row.source_id,
                row.camera_id,
                row.name,
                row.url_suffix,
                row.sort_order,
                row.created_at,
                row.updated_at,
            )
            for row in (
                await reading_session.scalars(
                    select(CameraSourceRow)
                    .where(CameraSourceRow.camera_id == camera.camera_id)
                    .order_by(CameraSourceRow.sort_order.asc())
                )
            ).all()
        )
    assert persisted is not None
    assert persisted.default_preview_source_id == camera.sources[1].source_id
    assert persisted.updated_at == changed_at
    assert persisted.sources == camera.sources
    assert source_rows_after == source_rows_before


async def test_camera_update_use_case_serializes_concurrent_writes_last_commit_wins(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """两个 PUT 按 Camera 行锁串行，后取得锁的合法写入成为最终数据库状态。"""

    camera = CameraBuilder().build(source_count=2, id_start=1_300)
    async with session_factory() as writing_session:
        writer = SQLAlchemyCameraUnitOfWork(writing_session)
        await writer.cameras.add(camera)
        await writer.commit()

    def command_with_name(name: str) -> UpdateCameraCommand:
        return UpdateCameraCommand(
            camera_id=camera.camera_id,
            name=name,
            ip_address=camera.ip_address,
            rtsp_port=camera.rtsp_port,
            username=camera.credentials.username,
            password=camera.credentials.password.reveal(),
            sources=tuple(
                UpdateCameraSourceCommand(
                    source_id=source.source_id,
                    name=source.name,
                    url_suffix=source.url_suffix,
                    is_default_preview=camera.is_default_preview(source.source_id),
                )
                for source in camera.sources
            ),
        )

    first_reached_commit = asyncio.Event()
    allow_first_commit = asyncio.Event()

    class BlockingCommitUnitOfWork(SQLAlchemyCameraUnitOfWork):
        """在持有 Camera 行锁时暂停第一笔事务，确定性验证第二笔等待。"""

        async def commit(self) -> None:
            first_reached_commit.set()
            await allow_first_commit.wait()
            await super().commit()

    async def run_first_update():
        async with session_factory() as session:
            return await update_camera(
                command_with_name("第一笔更新"),
                uow=BlockingCommitUnitOfWork(session),
                stream_gateway=FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=NOW)),
                id_generator=FixedIdGenerator(()),
                clock=FixedClock(NOW.replace(microsecond=1)),
            )

    async def run_second_update():
        async with session_factory() as session:
            return await update_camera(
                command_with_name("第二笔更新"),
                uow=SQLAlchemyCameraUnitOfWork(session),
                stream_gateway=FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=NOW)),
                id_generator=FixedIdGenerator(()),
                clock=FixedClock(NOW.replace(microsecond=2)),
            )

    first_task = asyncio.create_task(run_first_update())
    await asyncio.wait_for(first_reached_commit.wait(), timeout=1)
    second_task = asyncio.create_task(run_second_update())
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(asyncio.shield(second_task), timeout=0.1)

    allow_first_commit.set()
    first_result, second_result = await asyncio.gather(first_task, second_task)
    assert first_result.camera.name == "第一笔更新"
    assert second_result.camera.name == "第二笔更新"

    async with session_factory() as reading_session:
        persisted = await SQLAlchemyCameraRepository(reading_session).get(camera.camera_id)
    assert persisted is not None
    assert persisted.name == "第二笔更新"


async def test_put_and_default_source_patch_serialize_on_same_camera_lock(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """PUT 持锁提交前 PATCH 必须等待，并基于 PUT 提交后的最新聚合继续写入。"""

    camera = CameraBuilder().build(source_count=2, id_start=1_400)
    async with session_factory() as writing_session:
        writer = SQLAlchemyCameraUnitOfWork(writing_session)
        await writer.cameras.add(camera)
        await writer.commit()

    put_command = UpdateCameraCommand(
        camera_id=camera.camera_id,
        name="PUT 更新后的名称",
        ip_address=camera.ip_address,
        rtsp_port=camera.rtsp_port,
        username=camera.credentials.username,
        password=camera.credentials.password.reveal(),
        sources=tuple(
            UpdateCameraSourceCommand(
                source_id=source.source_id,
                name=source.name,
                url_suffix=source.url_suffix,
                is_default_preview=camera.is_default_preview(source.source_id),
            )
            for source in camera.sources
        ),
    )
    patch_command = SetDefaultPreviewSourceCommand(
        camera_id=camera.camera_id,
        source_id=camera.sources[1].source_id,
    )
    put_reached_commit = asyncio.Event()
    allow_put_commit = asyncio.Event()

    class BlockingPutUnitOfWork(SQLAlchemyCameraUnitOfWork):
        """PUT 保存完整聚合并持有行锁后暂停，让 PATCH 的等待行为可确定复现。"""

        async def commit(self) -> None:
            put_reached_commit.set()
            await allow_put_commit.wait()
            await super().commit()

    async def run_put():
        async with session_factory() as session:
            return await update_camera(
                put_command,
                uow=BlockingPutUnitOfWork(session),
                stream_gateway=FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=NOW)),
                id_generator=FixedIdGenerator(()),
                clock=FixedClock(NOW.replace(microsecond=1)),
            )

    async def run_patch():
        async with session_factory() as session:
            return await set_default_preview_source(
                patch_command,
                uow=SQLAlchemyCameraUnitOfWork(session),
                clock=FixedClock(NOW.replace(microsecond=2)),
            )

    put_task = asyncio.create_task(run_put())
    await asyncio.wait_for(put_reached_commit.wait(), timeout=1)
    patch_task = asyncio.create_task(run_patch())
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(asyncio.shield(patch_task), timeout=0.1)

    allow_put_commit.set()
    put_result, patch_result = await asyncio.gather(put_task, patch_task)
    assert put_result.camera.name == "PUT 更新后的名称"
    assert patch_result.default_preview_source_id == camera.sources[1].source_id

    async with session_factory() as reading_session:
        persisted = await SQLAlchemyCameraRepository(reading_session).get(camera.camera_id)
    assert persisted is not None
    assert persisted.name == "PUT 更新后的名称"
    assert persisted.default_preview_source_id == camera.sources[1].source_id
    assert persisted.updated_at == NOW.replace(microsecond=2)
