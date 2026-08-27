"""媒体对账 Reader 与 PostgreSQL session advisory lock 集成测试。"""

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, event, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.modules.cameras.application.reconciliation import (
    ReconciliationOutcome,
    reconcile_once,
)
from app.modules.cameras.domain import CameraAggregateCorruptedError
from app.modules.cameras.persistence.mapper import camera_to_rows
from app.modules.cameras.persistence.models import CameraRow, CameraSourceRow
from app.modules.cameras.persistence.reconciliation import (
    MEDIA_RECONCILIATION_LOCK_KEY,
    PostgreSQLMediaReconciliationLease,
)
from app.modules.stream_gateway.ports import (
    ConfiguredPath,
    ConfiguredPathSnapshot,
    DesiredSource,
    RuntimePathSnapshot,
)
from tests.core.database.test_migrations import (
    temporary_database,
    validate_test_database_url,
)
from tests.modules.cameras.builders import CameraBuilder

pytestmark = pytest.mark.anyio

BACKEND_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def migrated_database_url() -> Iterator[URL]:
    """创建只属于本模块的已迁移 PostgreSQL 数据库。"""

    raw_test_url = os.getenv("TEST_DATABASE_URL")
    if raw_test_url is None:
        pytest.skip("未配置 TEST_DATABASE_URL")
    raw_application_url = os.getenv("DATABASE_URL")
    if raw_application_url is None:
        pytest.fail("验证测试数据库隔离性需要配置 DATABASE_URL")

    configured_url = validate_test_database_url(raw_test_url, raw_application_url)
    assert configured_url.database is not None
    database_stem = configured_url.database.removesuffix("_test")
    reconciliation_url = configured_url.set(database=f"{database_stem}_reconciliation_test")
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    alembic_config.attributes["database_url"] = reconciliation_url.render_as_string(
        hide_password=False
    )
    with temporary_database(reconciliation_url):
        command.upgrade(alembic_config, "head")
        yield reconciliation_url


@pytest.fixture
async def engine(migrated_database_url: URL) -> AsyncIterator[AsyncEngine]:
    """每例使用最小连接池并清空 Camera 表，覆盖 pool_size=1 场景。"""

    database_engine = create_async_engine(
        migrated_database_url,
        hide_parameters=True,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        pool_timeout=1,
    )
    async with database_engine.begin() as connection:
        await connection.execute(delete(CameraSourceRow))
        await connection.execute(delete(CameraRow))
    try:
        yield database_engine
    finally:
        async with database_engine.begin() as connection:
            await connection.execute(delete(CameraSourceRow))
            await connection.execute(delete(CameraRow))
        await database_engine.dispose()


async def seed_camera(engine: AsyncEngine, camera) -> None:
    """用真实 ORM 事务写入一个合法聚合，后续 Reader 只能只读访问。"""

    camera_row, source_rows = camera_to_rows(camera)
    async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
        session.add(camera_row)
        session.add_all(source_rows)


class RecordingGateway:
    """在内存中模拟 MediaMTX 配置，验证最小连接池下不会申请第二条数据库连接。"""

    def __init__(self) -> None:
        self.configured: dict[str, ConfiguredPath] = {}
        self.operations: list[tuple[str, str]] = []

    async def fetch_config_path_snapshot(self) -> ConfiguredPathSnapshot:
        from datetime import UTC, datetime

        return ConfiguredPathSnapshot(
            paths=tuple(self.configured.values()),
            checked_at=datetime.now(UTC),
        )

    async def ensure_path(self, desired_source: DesiredSource) -> None:
        self.operations.append(("ensure", desired_source.path_name))
        self.configured[desired_source.path_name] = ConfiguredPath(
            desired_source.path_name,
            desired_source.source_url,
            False,
        )

    async def release_path(self, source_id) -> None:
        self.operations.append(("release", str(source_id)))
        self.configured.pop(str(source_id), None)

    async def fetch_runtime_path_snapshot(self) -> RuntimePathSnapshot:
        raise AssertionError("媒体对账不应读取运行态 Path")

    def whep_url_for(self, source_id) -> str:
        raise AssertionError(f"媒体对账不应构造 WHEP URL：{source_id}")


async def current_session_advisory_lock_count(engine: AsyncEngine) -> int:
    """查询池中当前物理连接持有的 advisory lock 数，防止重入掩盖泄漏。"""

    async with engine.connect() as connection:
        count = await connection.scalar(
            text(
                "SELECT count(*) FROM pg_locks "
                "WHERE locktype = 'advisory' AND pid = pg_backend_pid()"
            )
        )
    assert count is not None
    return int(count)


async def test_reader_uses_one_left_join_and_minimum_pool_completes_reconciliation(
    engine: AsyncEngine,
) -> None:
    """持锁 Reader 复用同一 Connection，单条 JOIN 重建后再执行远端写入。"""

    camera = CameraBuilder().build(source_count=2)
    await seed_camera(engine, camera)
    select_statements: list[str] = []

    def capture_statement(_conn, _cursor, statement, _parameters, _context, _many) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            select_statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", capture_statement)
    try:
        lease = PostgreSQLMediaReconciliationLease(engine)
        gateway = RecordingGateway()

        result = await reconcile_once(lease, gateway)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture_statement)

    assert result.outcome is ReconciliationOutcome.SUCCESS
    assert result.ensured_count == 2
    assert len([sql for sql in select_statements if "LEFT OUTER JOIN" in sql.upper()]) == 1
    assert await current_session_advisory_lock_count(engine) == 0


async def test_competing_lease_returns_none_and_exception_releases_lock(
    migrated_database_url: URL,
) -> None:
    """两个实例只有一个取得锁，业务异常后另一个实例可立即取得。"""

    engine = create_async_engine(
        migrated_database_url,
        hide_parameters=True,
        pool_size=2,
        max_overflow=0,
    )
    first_lease = PostgreSQLMediaReconciliationLease(engine)
    second_lease = PostgreSQLMediaReconciliationLease(engine)
    try:
        with pytest.raises(RuntimeError, match="测试异常"):
            async with first_lease.acquire() as first_reader:
                assert first_reader is not None
                async with second_lease.acquire() as second_reader:
                    assert second_reader is None
                raise RuntimeError("测试异常")

        async with second_lease.acquire() as reader_after_error:
            assert reader_after_error is not None
    finally:
        await engine.dispose()


async def test_cancelled_lease_holder_releases_lock(engine: AsyncEngine) -> None:
    """任务取消后 finally 解锁，连接池不会保留 session lock。"""

    entered = asyncio.Event()
    lease = PostgreSQLMediaReconciliationLease(engine)

    async def hold_until_cancelled() -> None:
        async with lease.acquire() as reader:
            assert reader is not None
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(hold_until_cancelled())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert await current_session_advisory_lock_count(engine) == 0
    async with lease.acquire() as reader_after_cancel:
        assert reader_after_cancel is not None


async def test_left_join_surfaces_camera_without_sources_as_corruption(
    engine: AsyncEngine,
) -> None:
    """损坏 Camera 仍出现在 LEFT JOIN 中，不能被全量 Reader 静默漏掉。"""

    camera = CameraBuilder().build(source_count=1)
    camera_row, _ = camera_to_rows(camera)
    async with AsyncSession(engine) as session, session.begin():
        session.add(camera_row)

    lease = PostgreSQLMediaReconciliationLease(
        engine,
        lock_key=MEDIA_RECONCILIATION_LOCK_KEY,
    )
    async with lease.acquire() as reader:
        assert reader is not None
        with pytest.raises(CameraAggregateCorruptedError):
            await reader.read_all()

    assert await current_session_advisory_lock_count(engine) == 0
