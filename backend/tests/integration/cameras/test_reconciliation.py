"""媒体对账 Reader 与 PostgreSQL session advisory lock 集成测试。"""

import asyncio

import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.modules.cameras.application.reconciliation import (
    ReconciliationOutcome,
    reconcile_once,
)
from app.modules.cameras.domain import CameraAggregateCorruptedError
from app.modules.cameras.persistence.mapper import camera_to_rows
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
from tests.support.cameras.builders import CameraBuilder

pytestmark = pytest.mark.anyio


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


async def test_读取器使用一次左连接且最小连接池可完成对账(
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


async def test_竞争租约返回空值且异常会释放锁(
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


async def test_租约持有者取消后释放锁(engine: AsyncEngine) -> None:
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


async def test_左连接将没有视频源的Camera报告为数据损坏(
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
