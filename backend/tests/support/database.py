"""真实 PostgreSQL 测试共用的安全建库、清理和 revision 查询辅助函数。

这里只提供测试 Setup，不包含断言或 pytest Fixture。调用方必须显式提供 TEST_DATABASE_URL，
并经过 ``validate_test_database_url`` 检查后才能创建数据库。
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from sqlalchemy import URL, make_url
from sqlalchemy.exc import ArgumentError

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def validate_test_database_url(test_database_url: str, application_database_url: str) -> URL:
    """解析并验证测试 URL，拒绝应用库、错误驱动和非测试库名。

    按数据库名拒绝应用库比完整 URL 比较更严格：即使主机不同，也不允许测试目标沿用
    应用数据库名称，从而降低环境变量错配时执行破坏性迁移命令的风险。
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
    无连接串的错误文本，并用 ``from None`` 切断包含底层调用参数的异常链。
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

    CREATE/DROP DATABASE 不能位于事务中，所以管理连接开启 autocommit。若同名库已存在
    则立即拒绝，绝不猜测其所有权；finally 也只清理由本上下文成功创建的数据库。
    """

    database_name = test_url.database
    assert database_name is not None
    admin_url = test_url.set(database="postgres")
    created = False

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
            # 先终止测试遗留连接，否则异步 Engine 的回收时序可能让 DROP DATABASE 失败。
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
