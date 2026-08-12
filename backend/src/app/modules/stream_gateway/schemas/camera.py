from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, SecretStr, model_validator

CameraStatus = Literal["configured", "online", "offline"]


class CameraCreate(BaseModel):
    camera_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    name: str = Field(min_length=1, max_length=128)
    source_url: SecretStr

    @model_validator(mode="after")
    def validate_source_url(self) -> Self:
        scheme = urlsplit(self.source_url.get_secret_value()).scheme.lower()
        if scheme not in {"rtsp", "rtsps"}:
            raise ValueError("source_url must use the rtsp or rtsps scheme")
        return self


class CameraUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    source_url: SecretStr | None = None

    @model_validator(mode="after")
    def validate_update(self) -> Self:
        if self.name is None and self.source_url is None:
            raise ValueError("at least one field must be provided")
        if self.source_url is not None:
            scheme = urlsplit(self.source_url.get_secret_value()).scheme.lower()
            if scheme not in {"rtsp", "rtsps"}:
                raise ValueError("source_url must use the rtsp or rtsps scheme")
        return self


class CameraResponse(BaseModel):
    camera_id: str
    name: str
    path: str
    status: CameraStatus
    whep_url: str
