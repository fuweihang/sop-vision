"""Validate and version one PostgreSQL-backed Worker configuration."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

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


def validate_record(record: TaskParameterRecord, resource_root: Path) -> LoadedWorker:
    try:
        definition = get_worker_definition(record.worker_type)
        config = definition.validate_config(
            record.task_id, record.config, resource_root
        )
    except (ValidationError, ValueError) as error:
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
