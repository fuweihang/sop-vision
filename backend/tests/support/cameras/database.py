"""Cameras PostgreSQL 集成测试共用的确定性 ORM 记录与计数辅助函数。"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from ipaddress import IPv4Address
from uuid import UUID

from alembic import command
from alembic.config import Config
from sqlalchemy import URL, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.cameras.persistence.models import CameraRow, CameraSourceRow
from tests.support.database import BACKEND_ROOT, temporary_database, validate_test_database_url

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


@contextmanager
def migrated_cameras_database(
    test_database_url: str,
    application_database_url: str,
) -> Iterator[URL]:
    """创建并迁移 Cameras integration 独占数据库。

    环境变量是否存在由 pytest Fixture 决定；此 helper 只负责复用安全 URL 校验、建库和迁移步骤，
    防止 Repository 与对账测试各自复制一套高风险数据库 Setup。
    """

    configured_url = validate_test_database_url(test_database_url, application_database_url)
    assert configured_url.database is not None
    database_stem = configured_url.database.removesuffix("_test")
    cameras_url = configured_url.set(database=f"{database_stem}_cameras_integration_test")

    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    alembic_config.attributes["database_url"] = cameras_url.render_as_string(hide_password=False)
    with temporary_database(cameras_url):
        command.upgrade(alembic_config, "head")
        yield cameras_url


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


async def row_counts(factory: async_sessionmaker[AsyncSession]) -> tuple[int, int]:
    """读取 Camera 与 Source 记录数，确保事务异常没有留下半套聚合。"""

    async with factory() as session:
        camera_count = await session.scalar(select(func.count()).select_from(CameraRow))
        source_count = await session.scalar(select(func.count()).select_from(CameraSourceRow))
    assert camera_count is not None
    assert source_count is not None
    return camera_count, source_count
