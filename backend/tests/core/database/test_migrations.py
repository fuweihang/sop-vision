"""Alembic 基线与专用 PostgreSQL 测试库的安全验收。

本模块是唯一读取 ``TEST_DATABASE_URL`` 的位置。它绝不回退到应用 ``DATABASE_URL``，
只创建本次测试确认不存在的 ``*_test`` 数据库，并且只清理由本上下文成功创建的目标。
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from psycopg import sql
from sqlalchemy import URL, make_url
from sqlalchemy.exc import ArgumentError

BACKEND_ROOT = Path(__file__).resolve().parents[3]


def validate_test_database_url(test_database_url: str, application_database_url: str) -> URL:
    """解析并验证测试 URL 的 fail-closed 隔离约束。

    除了限制显式 psycopg 驱动和 ``_test`` 后缀，还按数据库名拒绝应用库。这里故意采用
    比完整 URL 比较更严格的规则：即使主机不同，也不允许测试目标沿用应用数据库名称，
    从而降低环境变量错配时执行 ``downgrade base`` 的风险。
    """

    try:
        test_url = make_url(test_database_url)
        application_url = make_url(application_database_url)
    except ArgumentError:
        raise RuntimeError("数据库测试 URL 必须是有效的 SQLAlchemy URL") from None

    if test_url.drivername != "postgresql+psycopg":
        raise RuntimeError("TEST_DATABASE_URL 必须使用 postgresql+psycopg 驱动")
    if not test_url.database or not test_url.database.endswith("_test"):
        raise RuntimeError("TEST_DATABASE_URL 的数据库名称必须以 _test 结尾")
    if test_url.database == application_url.database:
        raise RuntimeError("TEST_DATABASE_URL 不得指向应用数据库")
    return test_url


def psycopg_connect_kwargs(url: URL) -> dict[str, Any]:
    """把 SQLAlchemy URL 转为 Psycopg 参数，并保留 SSL 等 query 配置。"""

    kwargs = url.translate_connect_args(username="user", database="dbname")
    kwargs.update(url.query)
    return {key: value for key, value in kwargs.items() if value is not None}


@contextmanager
def postgres_connection(url: URL, *, autocommit: bool = False) -> Iterator[psycopg.Connection]:
    """提供不会在异常链中泄露连接参数的 Psycopg 连接。

    Psycopg 连接失败 traceback 的局部变量可能包含明文 password，因此边界处只抛稳定、
    无连接串的错误文本，并使用 ``from None`` 切断包含底层调用参数的异常链。
    """

    try:
        connection = psycopg.connect(
            autocommit=autocommit,
            **psycopg_connect_kwargs(url),
        )
    except psycopg.Error:
        raise RuntimeError("无法连接 PostgreSQL 测试服务器") from None

    try:
        with connection:
            yield connection
    except psycopg.Error:
        raise RuntimeError("PostgreSQL 测试数据库操作失败") from None


@contextmanager
def temporary_database(test_url: URL) -> Iterator[None]:
    """创建并最终删除一座由本次测试独占的临时数据库。

    ``CREATE/DROP DATABASE`` 不能位于事务中，所以管理连接开启 autocommit。若同名库已
    存在则立即拒绝，绝不猜测其所有权。finally 只在本上下文成功创建数据库后执行清理；
    删除前终止残留测试连接，避免迁移 Engine 的连接回收时序导致 DROP 失败。
    """

    database_name = test_url.database
    assert database_name is not None
    admin_url = test_url.set(database="postgres")
    created = False

    # 始终通过 postgres 管理库创建目标库，不能连接尚不存在的测试库本身。
    with postgres_connection(admin_url, autocommit=True) as connection:
        database_exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (database_name,),
        ).fetchone()
        if database_exists is not None:
            raise RuntimeError("拒绝接管现有测试数据库")
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
        created = True

    try:
        yield
    finally:
        if created:
            # created 标志保证本分支永远不会删除测试运行前就存在的数据库。
            with postgres_connection(admin_url, autocommit=True) as connection:
                connection.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (database_name,),
                )
                connection.execute(
                    sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name))
                )


def current_revision(database_url: URL) -> str | None:
    """直接读取 version table，避免只用 Alembic 命令退出码判断迁移结果。"""

    with postgres_connection(database_url) as connection:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    return None if row is None else str(row[0])


def camera_tables_exist(database_url: URL) -> bool:
    """确认两张 Camera 表是否同时存在。"""

    with postgres_connection(database_url) as connection:
        rows = connection.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name IN ('cameras', 'camera_sources')"
        ).fetchall()
    return {str(row[0]) for row in rows} == {"cameras", "camera_sources"}


def assert_camera_schema(database_url: URL) -> None:
    """从 PostgreSQL 系统目录验收无外键表、稳定约束和索引。"""

    with postgres_connection(database_url) as connection:
        constraints = connection.execute(
            "SELECT conname, contype, condeferrable, condeferred "
            "FROM pg_constraint "
            "WHERE conrelid IN ('cameras'::regclass, 'camera_sources'::regclass)"
        ).fetchall()
        indexes = connection.execute(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'public' AND tablename = 'camera_sources'"
        ).fetchall()
        url_suffix_collation = connection.execute(
            "SELECT collation_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'camera_sources' "
            "AND column_name = 'url_suffix'"
        ).fetchone()

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


def test_empty_postgresql_database_upgrade_downgrade_upgrade_chain() -> None:
    """在真实空 PostgreSQL 库逐步断言基线 → head → base → head revision。

    未配置测试 URL 时普通单元测试可以跳过本例；CI/验收显式提供该变量后，会自动创建、
    验证并清理测试库。应用 URL 仍是必需的，因为它是隔离校验的比较基准。
    """

    raw_test_url = os.getenv("TEST_DATABASE_URL")
    if raw_test_url is None:
        pytest.skip("未配置 TEST_DATABASE_URL")

    raw_application_url = os.getenv("DATABASE_URL")
    if raw_application_url is None:
        pytest.fail("验证测试数据库隔离性需要配置 DATABASE_URL")

    test_url = validate_test_database_url(raw_test_url, raw_application_url)
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    alembic_config.attributes["database_url"] = test_url.render_as_string(hide_password=False)
    head_revision = ScriptDirectory.from_config(alembic_config).get_current_head()

    with temporary_database(test_url):
        # 先停在上一版本，显式覆盖从既有基线升级的路径。
        command.upgrade(alembic_config, "0001_database_runtime")
        assert current_revision(test_url) == "0001_database_runtime"
        assert not camera_tables_exist(test_url)

        command.upgrade(alembic_config, "head")
        assert current_revision(test_url) == head_revision
        assert camera_tables_exist(test_url)
        assert_camera_schema(test_url)
        command.check(alembic_config)

        command.downgrade(alembic_config, "0001_database_runtime")
        assert current_revision(test_url) == "0001_database_runtime"
        assert not camera_tables_exist(test_url)

        command.downgrade(alembic_config, "base")
        assert current_revision(test_url) is None

        command.upgrade(alembic_config, "head")
        assert current_revision(test_url) == head_revision
        assert_camera_schema(test_url)
        command.check(alembic_config)
