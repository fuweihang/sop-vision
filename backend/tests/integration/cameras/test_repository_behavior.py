"""Camera Repository、UoW 与查询流程的真实 PostgreSQL 集成测试。"""

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.cameras.api.mappers import camera_detail_from_runtime
from app.modules.cameras.application import (
    CameraConstraintViolationError,
    CameraConstraintViolationKind,
    CameraListCriteria,
    CameraNotFoundError,
    CreateCameraCommand,
    CreateCameraSourceCommand,
    create_camera,
    get_camera_detail,
    list_cameras,
)
from app.modules.cameras.domain import CameraAggregateCorruptedError, CameraSourceChange
from app.modules.cameras.persistence.models import CameraSourceRow
from app.modules.cameras.persistence.repository import SQLAlchemyCameraRepository
from app.modules.cameras.persistence.uow import SQLAlchemyCameraUnitOfWork
from app.modules.stream_gateway.ports import RuntimePath, RuntimePathSnapshot
from tests.support.cameras.builders import (
    CameraBuilder,
    FixedClock,
    FixedIdGenerator,
    uuid4_from_index,
)
from tests.support.cameras.constants import CAMERA_LEAK_SENTINEL
from tests.support.cameras.database import CAMERA_A, NOW, SOURCE_A, make_camera, row_counts
from tests.support.cameras.fakes import FakeStreamGateway
from tests.support.cameras.repository_contract import assert_camera_repository_contract

pytestmark = pytest.mark.anyio


async def test_Camera仓储支持往返字面搜索和事务可见性(
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


async def test_SQLAlchemy仓储通过共享聚合检查(
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


async def test_Camera仓储保存交换和删除回滚保持原子性(
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


async def test_工作单元在提交时转换延迟约束错误并恢复会话(
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


async def test_创建流程在调用媒体网关前回滚刷写冲突(
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


async def test_Camera仓储拒绝损坏数据行而非返回不完整Camera(
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


async def test_Camera详情读取有序PostgreSQL聚合并映射完整响应(
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


async def test_Camera列表结束读取事务后获取PostgreSQL分页结果(
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


async def test_聚合加锁读取串行化同一Camera的更新意图(
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


async def test_Camera删除与并发保存串行化且不留下孤儿视频源(
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
