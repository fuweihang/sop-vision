from functools import lru_cache
from typing import Annotated, Any

from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def split_comma_separated(value: Any) -> Any:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


CommaSeparatedList = Annotated[list[str], NoDecode, BeforeValidator(split_comma_separated)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    app_name: str = "SOP Vision Stream Gateway"
    mediamtx_api_url: str = "http://mediamtx:9997"
    mediamtx_api_timeout: float = Field(default=5.0, gt=0)
    public_webrtc_base_url: str = "http://localhost:8889"
    stream_gateway_cors_origins: CommaSeparatedList = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
