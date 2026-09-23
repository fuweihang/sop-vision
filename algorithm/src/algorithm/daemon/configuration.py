"""Validate and version one PostgreSQL-backed Worker configuration."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ValidationError

from algorithm.common.config import AlgorithmConfig, AlgorithmConfigError
from algorithm.database import TaskParameterRecord

from .registry import get_worker_definition


class WorkerConfigurationError(ValueError):
    """Stored parameters do not conform to their registered Worker schema."""


@dataclass(frozen=True, slots=True)
class LoadedWorker:
    task_id: str
    worker_type: str
    config: BaseModel
    revision: str
    updated_at: datetime


def validate_record(
    record: TaskParameterRecord,
    outer_config: AlgorithmConfig,
) -> LoadedWorker:
    """合并数据库任务参数与外围配置，生成子进程实际使用的完整配置。"""

    try:
        definition = get_worker_definition(record.worker_type)
        config = definition.validate_config(
            record.task_id,
            record.config,
            redis_url=outer_config.redis_url,
            model_path=outer_config.model_path_for(record.worker_type),
        )
    except (AlgorithmConfigError, ValidationError, ValueError) as error:
        raise WorkerConfigurationError(_safe_error_detail(error)) from error
    return LoadedWorker(
        task_id=record.task_id,
        worker_type=record.worker_type,
        config=config,
        revision=_config_revision(record.worker_type, config),
        updated_at=record.updated_at,
    )


def _config_revision(worker_type: str, config: BaseModel) -> str:
    normalized = json.dumps(
        {"type": worker_type, "config": config.model_dump(mode="json")},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(normalized).hexdigest()}"


def _safe_error_detail(error: Exception) -> str:
    """Return field locations without echoing credential-bearing input values."""

    if isinstance(error, ValidationError):
        details = []
        for item in error.errors(include_url=False, include_input=False):
            location = ".".join(str(part) for part in item["loc"])
            details.append(f"{location}: {item['msg']}")
        return "; ".join(details)
    return str(error)
