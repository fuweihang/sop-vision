from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    app_name: str = "SOP Vision Stream Gateway"
    mediamtx_api_url: str = "http://mediamtx:9997"
    mediamtx_api_timeout: float = Field(default=5.0, gt=0)
    public_webrtc_base_url: str = "http://localhost:8889"
    stream_gateway_cors_origins: str = "http://localhost:5173"

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.stream_gateway_cors_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
