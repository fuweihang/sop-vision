"""应用配置解析及数据库凭据脱敏回归测试。"""

import logging
from collections.abc import Iterator

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings, get_settings


@pytest.fixture(autouse=True)
def isolate_settings_cache() -> Iterator[None]:
    """在每个配置测试前后清空生产配置缓存，隔离环境变量变更。

    ``app.main`` 在测试收集阶段可能已经调用过 ``get_settings``。如果直接复用该缓存，
    测试通过 monkeypatch 设置或删除的环境变量不会参与本次解析；测试结束后再次清空，
    则可防止测试期间生成的配置泄漏到同一进程后续用例。
    """

    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


def test_cors_origins_are_parsed_from_comma_separated_environment_variable(
    monkeypatch,
) -> None:
    """逗号分隔的 CORS 环境变量会规范化为去空白列表。"""

    monkeypatch.setenv(
        "BACKEND_CORS_ORIGINS",
        "http://localhost:8000, https://vision.example.com",
    )

    # 模块级 fixture 已清空缓存，因此本次调用会读取刚刚写入的环境变量。
    settings = get_settings()

    assert settings.backend_cors_origins == [
        "http://localhost:8000",
        "https://vision.example.com",
    ]


def test_database_url_is_required(monkeypatch) -> None:
    """缺少 DATABASE_URL 时应在启动配置阶段确定失败。"""

    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError) as error:
        # 直接验证生产加载入口，确保缺少必填环境变量时会立即失败。
        get_settings()

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
        # 显式包装为字段声明的 SecretStr；AfterValidator 仍会校验其中的原始 URL。
        Settings(database_url=SecretStr(database_url))

    assert "test-password" not in str(error.value)


def test_database_url_is_redacted_from_settings_representations() -> None:
    """Settings 的 repr、str 和 JSON 序列化都只输出 SecretStr 掩码。"""

    password = "config-secret-password"
    settings = Settings(
        database_url=SecretStr(f"postgresql+psycopg://sop_vision:{password}@localhost/sop_vision")
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
            Settings(
                database_url=SecretStr(f"postgresql+psycopg://sop_vision:{password}@localhost")
            )
        except ValidationError:
            logging.getLogger("app.config.test").exception("数据库配置无效")
        else:
            pytest.fail("无效的 DATABASE_URL 被错误接受")

    assert password not in caplog.text
