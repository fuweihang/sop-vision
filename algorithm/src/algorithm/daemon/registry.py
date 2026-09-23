"""受信任的 Worker 类型注册表。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from algorithm.workers.detector.app import run_detector
from algorithm.workers.detector.config import DetectorConfig
from algorithm.workers.tracker.app import run_tracker
from algorithm.workers.tracker.config import TrackerConfig

WorkerEntrypoint = Callable[..., None]


@dataclass(frozen=True, slots=True)
class WorkerDefinition:
    config_model: type[BaseModel]
    entrypoint: WorkerEntrypoint

    def validate_config(
        self,
        task_id: str,
        value: dict[str, Any],
        *,
        redis_url: str,
        model_path: Path,
    ) -> BaseModel:
        if "task_id" in value:
            raise ValueError("task_id must be declared only as the workers object key")
        outer_fields = sorted({"redis_url", "model_path"} & value.keys())
        if outer_fields:
            fields = ", ".join(outer_fields)
            raise ValueError(f"任务参数不能包含外围配置字段：{fields}")
        return self.config_model.model_validate(
            {
                "task_id": task_id,
                **value,
                "redis_url": redis_url,
                "model_path": model_path,
            }
        )

    def parameter_schema(self) -> dict[str, Any]:
        """返回任务可填写字段，不暴露由外围 TOML 管理的运行参数。"""

        schema = self.config_model.model_json_schema(mode="validation")
        properties = schema.get("properties")
        if isinstance(properties, dict):
            for field in ("task_id", "redis_url", "model_path"):
                properties.pop(field, None)
        required = schema.get("required")
        if isinstance(required, list):
            hidden_fields = {"task_id", "redis_url", "model_path"}
            schema["required"] = [
                item for item in required if item not in hidden_fields
            ]
        return schema


WORKER_REGISTRY: dict[str, WorkerDefinition] = {
    "detector": WorkerDefinition(DetectorConfig, run_detector),
    "tracker": WorkerDefinition(TrackerConfig, run_tracker),
}


def get_worker_definition(worker_type: str) -> WorkerDefinition:
    try:
        return WORKER_REGISTRY[worker_type]
    except KeyError as error:
        raise ValueError(f"unknown worker type: {worker_type!r}") from error


def worker_type_names() -> tuple[str, ...]:
    return tuple(sorted(WORKER_REGISTRY))
