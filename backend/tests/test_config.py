"""应用配置解析及数据库凭据脱敏回归测试。"""

import logging
import re
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


@pytest.mark.parametrize(
    ("field", "value", "expected_message"),
    [
        ("mediamtx_api_url", "ftp://mediamtx:9997", "绝对 HTTP(S) URL"),
        ("mediamtx_api_url", "http://user:secret@mediamtx:9997", "不能包含凭据"),
        ("mediamtx_api_url", "http://mediamtx:9997/control", "不能包含路径前缀"),
        ("mediamtx_api_url", "http://mediamtx:9997?token=secret", "query 或 fragment"),
        ("public_webrtc_base_url", "//vision.example/media", "绝对 HTTP(S) URL"),
        (
            "public_webrtc_base_url",
            "https://user:secret@vision.example/media",
            "不能包含凭据",
        ),
        (
            "public_webrtc_base_url",
            "https://vision.example/media#player",
            "query 或 fragment",
        ),
    ],
)
def test_media_base_urls_fail_during_settings_validation(
    field: str,
    value: str,
    expected_message: str,
) -> None:
    """媒体部署地址错误必须阻止启动，而不是延迟成运行态 OFFLINE。"""

    with pytest.raises(ValidationError, match=re.escape(expected_message)):
        Settings(
            database_url=SecretStr(
                "postgresql+psycopg://sop_vision:sop_vision@localhost/sop_vision"
            ),
            **{field: value},
        )


def test_public_webrtc_base_url_accepts_reverse_proxy_path_prefix() -> None:
    """WHEP 可部署在反向代理子路径下，而 Control API 仍固定为主机根路径。"""

    settings = Settings(
        database_url=SecretStr("postgresql+psycopg://sop_vision:sop_vision@localhost/sop_vision"),
        mediamtx_api_url="https://mediamtx.internal:9997/",
        public_webrtc_base_url="https://vision.example/media/webrtc/",
    )

    assert settings.mediamtx_api_url.endswith("/")
    assert settings.public_webrtc_base_url.endswith("/media/webrtc/")


def test_media_reconciliation_defaults_and_environment_values(monkeypatch) -> None:
    """周期配置使用文档默认值，也能从环境按秒解析为浮点数。"""

    defaults = Settings(
        database_url=SecretStr("postgresql+psycopg://sop_vision:sop_vision@localhost/sop_vision")
    )
    assert defaults.media_reconciliation_interval_seconds == 30
    assert defaults.media_reconciliation_max_backoff_seconds == 300

    monkeypatch.setenv("MEDIA_RECONCILIATION_INTERVAL_SECONDS", "12.5")
    monkeypatch.setenv("MEDIA_RECONCILIATION_MAX_BACKOFF_SECONDS", "90")
    loaded = get_settings()
    assert loaded.media_reconciliation_interval_seconds == 12.5
    assert loaded.media_reconciliation_max_backoff_seconds == 90


def test_media_reconciliation_max_backoff_cannot_be_shorter_than_interval() -> None:
    """错误退避关系必须在启动前失败，不能让长期故障比正常轮询更频繁。"""

    with pytest.raises(ValidationError, match="不能小于正常周期"):
        Settings(
            database_url=SecretStr(
                "postgresql+psycopg://sop_vision:sop_vision@localhost/sop_vision"
            ),
            media_reconciliation_interval_seconds=60,
            media_reconciliation_max_backoff_seconds=30,
        )


def test_backend_logging_defaults_are_console_info(monkeypatch) -> None:
    """Backend 日志默认适合人工查看，并避免默认输出 DEBUG 噪声。"""

    monkeypatch.delenv("BACKEND_LOG_LEVEL", raising=False)
    monkeypatch.delenv("UVICORN_LOG_LEVEL", raising=False)
    monkeypatch.delenv("BACKEND_LOG_FORMAT", raising=False)
    settings = Settings(
        database_url=SecretStr("postgresql+psycopg://sop_vision:sop_vision@localhost/sop_vision")
    )

    assert settings.backend_log_level == "info"
    assert settings.backend_log_format == "console"


def test_backend_log_level_prefers_new_environment_variable(monkeypatch) -> None:
    """新变量优先于旧 Uvicorn 变量，避免迁移期间出现两个有效值时行为不确定。"""

    monkeypatch.setenv("BACKEND_LOG_LEVEL", "error")
    monkeypatch.setenv("UVICORN_LOG_LEVEL", "debug")

    assert get_settings().backend_log_level == "error"


def test_backend_log_level_falls_back_to_legacy_uvicorn_variable(monkeypatch) -> None:
    """未设置新变量的旧部署继续沿用原级别，不会静默退回 info。"""

    monkeypatch.delenv("BACKEND_LOG_LEVEL", raising=False)
    monkeypatch.setenv("UVICORN_LOG_LEVEL", "warning")

    assert get_settings().backend_log_level == "warning"


@pytest.mark.parametrize(
    ("environment_name", "value"),
    [
        ("BACKEND_LOG_LEVEL", "trace"),
        ("UVICORN_LOG_LEVEL", "verbose"),
        ("BACKEND_LOG_FORMAT", "pretty"),
    ],
)
def test_backend_logging_rejects_unsupported_environment_values(
    environment_name: str,
    value: str,
    monkeypatch,
) -> None:
    """非法日志配置在服务器启动前失败，不能由不同 Logger 各自猜测回退值。"""

    monkeypatch.delenv("BACKEND_LOG_LEVEL", raising=False)
    monkeypatch.delenv("UVICORN_LOG_LEVEL", raising=False)
    monkeypatch.setenv(environment_name, value)

    with pytest.raises(ValidationError):
        get_settings()
