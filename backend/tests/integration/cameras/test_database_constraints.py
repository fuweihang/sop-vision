"""Camera PostgreSQL 表结构、约束和跨表完整性巡检测试。"""

from ipaddress import IPv6Address

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.cameras.persistence.integrity import (
    ReferenceIntegrityIssueKind,
    scan_reference_integrity,
)
from app.modules.cameras.persistence.models import CameraSourceRow
from tests.support.cameras.database import (
    CAMERA_A,
    CAMERA_B,
    CAMERA_C,
    CAMERA_D,
    ORPHAN_CAMERA,
    SOURCE_A,
    SOURCE_B,
    SOURCE_C,
    SOURCE_MISSING,
    SOURCE_ORPHAN,
    make_camera,
    make_source,
    row_counts,
)

pytestmark = pytest.mark.anyio


async def test_PostgreSQL单表约束保持生效(
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


async def test_PostgreSQL模型保留预期约束和索引(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Camera 表结构必须保留 Repository 错误转换依赖的约束名及大小写规则。"""

    async with session_factory() as session:
        constraints = (
            await session.execute(
                text(
                    "SELECT conname, contype, condeferrable, condeferred "
                    "FROM pg_constraint "
                    "WHERE conrelid IN ('cameras'::regclass, 'camera_sources'::regclass)"
                )
            )
        ).all()
        indexes = (
            await session.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = 'public' AND tablename = 'camera_sources'"
                )
            )
        ).all()
        url_suffix_collation = (
            await session.execute(
                text(
                    "SELECT collation_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'camera_sources' "
                    "AND column_name = 'url_suffix'"
                )
            )
        ).one()

    constraint_by_name = {
        str(name): (str(kind), bool(deferrable), bool(deferred))
        for name, kind, deferrable, deferred in constraints
    }
    assert all(kind != "f" for kind, _, _ in constraint_by_name.values())
    assert constraint_by_name == {
        "ck_camera_sources_sort_order_non_negative": ("c", False, False),
        "ck_cameras_ip_address_ipv4": ("c", False, False),
        "ck_cameras_rtsp_port_range": ("c", False, False),
        "pk_camera_sources": ("p", False, False),
        "pk_cameras": ("p", False, False),
        "uq_camera_sources_camera_id_sort_order": ("u", True, True),
        "uq_camera_sources_camera_id_url_suffix": ("u", True, True),
    }
    assert "ix_camera_sources_camera_id" in {str(row[0]) for row in indexes}
    assert url_suffix_collation == ("C",)


async def test_主键拒绝重复的Camera和视频源ID(
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


async def test_视频源后缀唯一性限定作用域且区分大小写(
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


async def test_延迟唯一约束允许交换视频源后缀和顺序(
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


async def test_完整性扫描检测全部跨表异常(
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
