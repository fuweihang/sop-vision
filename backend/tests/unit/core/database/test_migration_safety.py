"""迁移配置和 PostgreSQL 测试辅助函数的隔离安全测试。"""

import psycopg
import pytest
from alembic.config import Config
from sqlalchemy import make_url

from tests.support.database import (
    BACKEND_ROOT,
    postgres_connection,
    validate_test_database_url,
)


def test_test_database_url_rejects_the_application_database() -> None:
    """即使名称带 _test，也不能让测试 URL 与应用库相同。"""

    application_url = "postgresql+psycopg://user:password@localhost/sop_vision_test"

    with pytest.raises(RuntimeError, match="不得指向"):
        validate_test_database_url(application_url, application_url)


def test_test_database_url_requires_test_suffix() -> None:
    """不带 _test 后缀的目标在建立任何数据库连接前被拒绝。"""

    with pytest.raises(RuntimeError, match="必须以 _test 结尾"):
        validate_test_database_url(
            "postgresql+psycopg://user:password@localhost/temporary",
            "postgresql+psycopg://user:password@localhost/sop_vision",
        )


def test_postgres_connection_error_does_not_expose_password(monkeypatch) -> None:
    """底层 Psycopg 失败经安全边界转换后不再携带密码。"""

    password = "migration-secret-password"
    database_url = make_url(f"postgresql+psycopg://user:{password}@localhost/sop_vision_test")

    def fail_to_connect(**_kwargs) -> None:
        raise psycopg.OperationalError("连接失败")

    monkeypatch.setattr(psycopg, "connect", fail_to_connect)

    with pytest.raises(RuntimeError) as error:
        with postgres_connection(database_url):
            pass

    assert password not in str(error.value)
    assert password not in repr(error.value)


def test_alembic_ini_contains_no_independent_logging_configuration() -> None:
    """Alembic 必须由应用统一配置日志，不能再从 ini 安装第二套 Handler/Formatter。"""

    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))

    for section in ("loggers", "handlers", "formatters"):
        assert not alembic_config.file_config.has_section(section)
