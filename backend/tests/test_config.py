"""应用配置解析及数据库凭据脱敏回归测试。"""

import logging

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_cors_origins_are_parsed_from_comma_separated_environment_variable(
    monkeypatch,
) -> None:
    """逗号分隔的 CORS 环境变量会规范化为去空白列表。"""

    monkeypatch.setenv(
        "BACKEND_CORS_ORIGINS",
        "http://localhost:8000, https://vision.example.com",
    )

    settings = Settings()

    assert settings.backend_cors_origins == [
        "http://localhost:8000",
        "https://vision.example.com",
    ]


def test_database_url_is_required(monkeypatch) -> None:
    """缺少 DATABASE_URL 时应在启动配置阶段确定失败。"""

    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError) as error:
        Settings()

    assert error.value.errors()[0]["loc"] == ("database_url",)


@pytest.mark.parametrize(
    "database_url",
    [
        "not-a-url",
        "postgresql://sop_vision:test-password@localhost/sop_vision",
        "postgresql+psycopg://sop_vision:test-password@localhost",
    ],
)
def test_database_url_rejects_invalid_values_without_exposing_password(database_url: str) -> None:
    """非法格式、错误驱动和缺少库名均被拒绝，且异常文本不含密码。"""

    with pytest.raises(ValidationError) as error:
        Settings(database_url=database_url)

    assert "test-password" not in str(error.value)


def test_database_url_is_redacted_from_settings_representations() -> None:
    """Settings 的 repr、str 和 JSON 序列化都只输出 SecretStr 掩码。"""

    password = "config-secret-password"
    settings = Settings(
        database_url=f"postgresql+psycopg://sop_vision:{password}@localhost/sop_vision"
    )

    assert password not in repr(settings)
    assert password not in str(settings)
    assert password not in settings.model_dump_json()
    assert settings.database_url.get_secret_value().endswith(f":{password}@localhost/sop_vision")


def test_database_url_validation_log_does_not_expose_password(caplog) -> None:
    """即使调用方记录完整 ValidationError traceback，日志也不能回显密码。"""

    password = "logged-config-password"

    with caplog.at_level(logging.ERROR):
        try:
            Settings(database_url=f"postgresql+psycopg://sop_vision:{password}@localhost")
        except ValidationError:
            logging.getLogger("app.config.test").exception("数据库配置无效")
        else:
            pytest.fail("无效的 DATABASE_URL 被错误接受")

    assert password not in caplog.text
