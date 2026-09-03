"""Cameras PostgreSQL 集成测试的独占数据库与每例清理 Fixture。"""

import os
from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy import delete
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.modules.cameras.persistence.models import CameraRow, CameraSourceRow
from tests.support.cameras.database import migrated_cameras_database


@pytest.fixture(scope="session")
def migrated_database_url() -> Iterator[URL]:
    """创建一座 Cameras integration 独占数据库，并升级到最新 revision。

    整层测试共享迁移结果可以避免每个文件重复建库。每个测试仍通过下方 Fixture 清空业务表，
    因此测试之间不会共享 Camera 数据。
    """

    raw_test_url = os.getenv("TEST_DATABASE_URL")
    if raw_test_url is None:
        pytest.fail("Cameras 集成测试需要配置 TEST_DATABASE_URL，不能跳过真实数据库验证")
    raw_application_url = os.getenv("DATABASE_URL")
    if raw_application_url is None:
        pytest.fail("验证测试数据库隔离性需要配置 DATABASE_URL")

    with migrated_cameras_database(raw_test_url, raw_application_url) as cameras_url:
        yield cameras_url


@pytest.fixture
async def session_factory(
    migrated_database_url: URL,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """提供真实 Repository 使用的 Session factory，并在每例前后清空 Camera 表。"""

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


@pytest.fixture
async def engine(migrated_database_url: URL) -> AsyncIterator[AsyncEngine]:
    """提供单连接池 Engine，验证对账持锁读取不会额外申请数据库连接。"""

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
