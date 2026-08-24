"""应用级配置定义及敏感数据库连接串校验。"""

from functools import lru_cache
from typing import Annotated, Any

from pydantic import AfterValidator, BeforeValidator, Field, SecretStr
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy import make_url
from sqlalchemy.exc import ArgumentError


def split_comma_separated(value: Any) -> Any:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


CommaSeparatedList = Annotated[list[str], NoDecode, BeforeValidator(split_comma_separated)]


def validate_database_url(value: SecretStr) -> SecretStr:
    """校验 SQLAlchemy URL，同时始终以 SecretStr 形式保留原始输入。

    校验发生在 SecretStr 解析后，错误信息只描述缺失项或驱动类型，不拼接原始 URL，
    避免应用启动失败时由 Pydantic/Uvicorn 日志回显数据库密码。
    """

    try:
        url = make_url(value.get_secret_value())
    except ArgumentError:
        raise ValueError("DATABASE_URL 必须是有效的 SQLAlchemy URL") from None

    if url.drivername != "postgresql+psycopg":
        raise ValueError("DATABASE_URL 必须使用 postgresql+psycopg 驱动")
    if not url.database:
        raise ValueError("DATABASE_URL 必须包含数据库名称")
    return value


# AfterValidator 接收的已经是脱敏 SecretStr，避免自定义校验器直接处理可打印明文。
DatabaseUrl = Annotated[SecretStr, AfterValidator(validate_database_url)]


class Settings(BaseSettings):
    """从进程环境读取 Backend 配置；DATABASE_URL 必须由部署环境显式提供。"""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
        # Pydantic 默认会在校验异常中附带 input_value；数据库配置必须关闭该行为。
        hide_input_in_errors=True,
    )

    app_name: str = "SOP Vision 后端"

    # 数据库 URL 属于敏感配置；其余字段只控制连接池与连接建立行为。
    database_url: DatabaseUrl
    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=5, ge=0)
    database_pool_timeout: float = Field(default=30.0, gt=0)
    database_pool_recycle: int = Field(default=1800, ge=-1)
    database_connect_timeout: int = Field(default=10, ge=1)
    database_echo: bool = False
    mediamtx_api_url: str = "http://mediamtx:9997"
    mediamtx_api_timeout: float = Field(default=5.0, gt=0)
    public_webrtc_base_url: str = "http://localhost:8889"
    backend_cors_origins: CommaSeparatedList = Field(
        default_factory=lambda: ["http://localhost:8000"]
    )


@lru_cache
def get_settings() -> Settings:
    """为生产应用复用配置；测试通过 create_app 参数注入独立 Settings。"""

    # BaseSettings 会在运行时从环境变量补齐必填字段；Pyright 无法从模型签名推导该行为。
    return Settings()  # pyright: ignore[reportCallIssue]
