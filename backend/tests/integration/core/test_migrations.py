"""Alembic 基线与专用 PostgreSQL 测试库的真实迁移验收。"""

import os

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.support.database import (
    BACKEND_ROOT,
    current_revision,
    temporary_database,
    validate_test_database_url,
)


def test_empty_postgresql_database_upgrade_downgrade_upgrade_chain() -> None:
    """在真实空 PostgreSQL 库验收 Alembic 基线 → head → base → head 的完整流程。

    只读取 TEST_DATABASE_URL，绝不回退到应用 DATABASE_URL。辅助函数会拒绝现有数据库，
    且只删除本测试成功创建的目标，避免误改开发或生产数据。
    """

    raw_test_url = os.getenv("TEST_DATABASE_URL")
    if raw_test_url is None:
        pytest.fail("Core 集成测试需要配置 TEST_DATABASE_URL，不能跳过真实数据库验证")

    raw_application_url = os.getenv("DATABASE_URL")
    if raw_application_url is None:
        pytest.fail("验证测试数据库隔离性需要配置 DATABASE_URL")

    test_url = validate_test_database_url(raw_test_url, raw_application_url)
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    alembic_config.attributes["database_url"] = test_url.render_as_string(hide_password=False)
    head_revision = ScriptDirectory.from_config(alembic_config).get_current_head()

    with temporary_database(test_url):
        command.upgrade(alembic_config, "0001_database_runtime")
        assert current_revision(test_url) == "0001_database_runtime"

        command.upgrade(alembic_config, "head")
        assert current_revision(test_url) == head_revision
        command.check(alembic_config)

        command.downgrade(alembic_config, "0001_database_runtime")
        assert current_revision(test_url) == "0001_database_runtime"

        command.downgrade(alembic_config, "base")
        assert current_revision(test_url) is None

        command.upgrade(alembic_config, "head")
        assert current_revision(test_url) == head_revision
        command.check(alembic_config)
