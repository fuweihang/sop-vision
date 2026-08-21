"""Blocking database and HTTP operations run by Viewer background threads."""

from __future__ import annotations

from typing import Any

import httpx

from algorithm.database import TaskParameterRecord, TaskParameterRepository


class DaemonClient:
    def __init__(self, base_url: str, *, timeout: float = 65.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def worker_types(self) -> tuple[str, ...]:
        response = httpx.get(f"{self.base_url}/v1/worker-types", timeout=self.timeout)
        response.raise_for_status()
        return tuple(item["worker_type"] for item in response.json()["worker_types"])

    def schema(self, worker_type: str) -> dict[str, Any]:
        response = httpx.get(
            f"{self.base_url}/v1/worker-types/{worker_type}/schema",
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def command(self, task_id: str, command: str) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/v1/workers/{task_id}/{command}",
            content=b"",
            timeout=self.timeout,
        )
        if response.is_error:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise RuntimeError(f"Daemon HTTP {response.status_code}: {detail}")
        return response.json()


def load_task(database_url: str, task_id: str) -> TaskParameterRecord | None:
    repository = TaskParameterRepository(database_url)
    try:
        return repository.get(task_id)
    finally:
        repository.close()


def save_task(
    database_url: str,
    task_id: str,
    worker_type: str,
    config: dict[str, Any],
) -> TaskParameterRecord:
    repository = TaskParameterRepository(database_url)
    try:
        return repository.upsert(task_id, worker_type, config)
    finally:
        repository.close()
