"""异步 Engine 配置透传及日志安全选项测试。"""

from unittest.mock import patch

from pydantic import SecretStr

from app.core.config import Settings
from app.core.database.engine import create_database_engine


def test_create_database_engine_uses_configured_pool_and_safe_logging() -> None:
    """连接池配置应完整透传，SQL 输出必须完全交给统一 Logger。"""

    settings = Settings(
        # Settings 的字段类型是 SecretStr；显式包装可让静态类型与运行时脱敏语义一致。
        database_url=SecretStr(
            "postgresql+psycopg://sop_vision:engine-password@localhost/sop_vision"
        ),
        database_pool_size=7,
        database_max_overflow=3,
        database_pool_timeout=12.5,
        database_pool_recycle=900,
        database_connect_timeout=4,
        database_echo=True,
    )

    with patch("app.core.database.engine.create_async_engine") as create_engine:
        engine = create_database_engine(settings)

    assert engine is create_engine.return_value
    create_engine.assert_called_once_with(
        settings.database_url.get_secret_value(),
        connect_args={"connect_timeout": 4},
        echo=False,
        hide_parameters=True,
        max_overflow=3,
        pool_pre_ping=True,
        pool_recycle=900,
        pool_size=7,
        pool_timeout=12.5,
    )
