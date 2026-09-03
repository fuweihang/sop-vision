"""Camera 写流程、默认预览源与并发写入的真实 PostgreSQL 集成测试。"""

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.cameras.application import (
    SetDefaultPreviewSourceCommand,
    UpdateCameraCommand,
    UpdateCameraSourceCommand,
    set_default_preview_source,
    update_camera,
)
from app.modules.cameras.persistence.models import CameraSourceRow
from app.modules.cameras.persistence.repository import SQLAlchemyCameraRepository
from app.modules.cameras.persistence.uow import SQLAlchemyCameraUnitOfWork
from app.modules.stream_gateway.ports import RuntimePathSnapshot
from tests.support.cameras.builders import (
    CameraBuilder,
    FixedClock,
    FixedIdGenerator,
    uuid4_from_index,
)
from tests.support.cameras.constants import CAMERA_LEAK_SENTINEL
from tests.support.cameras.database import NOW, row_counts
from tests.support.cameras.fakes import FakeStreamGateway

pytestmark = pytest.mark.anyio


async def test_Camera更新流程先持久化完整聚合再调用媒体网关(
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


async def test_默认预览源流程只持久化默认ID和Camera时间(
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


async def test_Camera更新流程串行化并发写入且最后提交生效(
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


async def test_完整更新和默认源修改使用同一Camera锁串行化(
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
