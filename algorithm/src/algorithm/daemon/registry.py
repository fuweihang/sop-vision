"""受信任的 Worker 类型注册表。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

from algorithm.workers.detector.app import run_detector
from algorithm.workers.detector.config import DetectorConfig


WorkerEntrypoint = Callable[..., None]


@dataclass(frozen=True, slots=True)
class WorkerDefinition:
    config_model: type[BaseModel]
    entrypoint: WorkerEntrypoint

    def validate_config(
        self,
        task_id: str,
        value: dict[str, Any],
        config_directory: Path,
    ) -> BaseModel:
        if "task_id" in value:
            raise ValueError("task_id must be declared only as the workers object key")
        config = self.config_model.model_validate({"task_id": task_id, **value})
        model_path = getattr(config, "model_path", None)
        if isinstance(model_path, Path) and not model_path.is_absolute():
            config = config.model_copy(
                update={"model_path": (config_directory / model_path).resolve()}
            )
        return config


WORKER_REGISTRY: dict[str, WorkerDefinition] = {
    "detector": WorkerDefinition(DetectorConfig, run_detector),
}


def get_worker_definition(worker_type: str) -> WorkerDefinition:
    try:
        return WORKER_REGISTRY[worker_type]
    except KeyError as error:
        raise ValueError(f"unknown worker type: {worker_type!r}") from error
