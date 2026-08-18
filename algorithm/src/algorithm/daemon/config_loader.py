"""读取、严格校验并版本化本地 ``config.json``。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .registry import get_worker_definition


class ConfigLoadError(ValueError):
    """配置文件不可读取、不可解析或不符合完整 Schema。"""


class RawWorkerEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: str = Field(min_length=1)
    config: dict[str, Any]


class RawAlgorithmConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    workers: dict[str, RawWorkerEntry]

    @field_validator("workers")
    @classmethod
    def validate_task_ids(
        cls, workers: dict[str, RawWorkerEntry]
    ) -> dict[str, RawWorkerEntry]:
        if any(not task_id.strip() for task_id in workers):
            raise ValueError("worker task IDs must not be empty")
        return workers


@dataclass(frozen=True, slots=True)
class LoadedWorker:
    task_id: str
    worker_type: str
    config: BaseModel
    revision: str


@dataclass(frozen=True, slots=True)
class LoadedAlgorithmConfig:
    source_path: Path
    workers: dict[str, LoadedWorker]


def load_config(path: Path) -> LoadedAlgorithmConfig:
    """读取并验证整个配置文件；任一 Worker 无效都会拒绝整份配置。"""

    source_path = path.expanduser().resolve()
    try:
        raw_text = source_path.read_text(encoding="utf-8")
        raw_data = json.loads(raw_text, object_pairs_hook=_object_without_duplicates)
        raw_config = RawAlgorithmConfig.model_validate(raw_data)
        workers: dict[str, LoadedWorker] = {}
        for task_id, entry in raw_config.workers.items():
            definition = get_worker_definition(entry.type)
            config = definition.validate_config(
                task_id,
                entry.config,
                source_path.parent,
            )
            revision = _config_revision(entry.type, config)
            workers[task_id] = LoadedWorker(
                task_id=task_id,
                worker_type=entry.type,
                config=config,
                revision=revision,
            )
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as error:
        raise ConfigLoadError(
            f"invalid configuration {source_path}: {_safe_error_detail(error)}"
        ) from error
    return LoadedAlgorithmConfig(source_path=source_path, workers=workers)


def _config_revision(worker_type: str, config: BaseModel) -> str:
    normalized = json.dumps(
        {
            "type": worker_type,
            "config": config.model_dump(mode="json"),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(normalized).hexdigest()}"


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _safe_error_detail(error: Exception) -> str:
    """报告字段位置和原因，但不把包含连接凭据的 input 回显到日志/API。"""

    if isinstance(error, ValidationError):
        details = []
        for item in error.errors(include_url=False, include_input=False):
            location = ".".join(str(part) for part in item["loc"])
            details.append(f"{location}: {item['msg']}")
        return "; ".join(details)
    return str(error)
