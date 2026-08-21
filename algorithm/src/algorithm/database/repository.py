"""Shared PostgreSQL repository for externally managed Worker parameters."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout


class RepositoryUnavailableError(RuntimeError):
    """The task parameter database cannot currently serve requests."""


@dataclass(frozen=True, slots=True)
class TaskParameterRecord:
    task_id: str
    worker_type: str
    config: dict[str, Any]
    updated_at: datetime


class TaskParameterRepository:
    """Small synchronous repository shared by the daemon and demo client."""

    def __init__(
        self,
        database_url: str,
        *,
        min_size: int = 0,
        max_size: int = 4,
        timeout: float = 5.0,
    ) -> None:
        self.database_url = database_url
        self._open_lock = threading.Lock()
        self._pool = ConnectionPool(
            conninfo=database_url,
            min_size=min_size,
            max_size=max_size,
            timeout=timeout,
            open=False,
            kwargs={"row_factory": dict_row},
        )

    def open(self) -> None:
        with self._open_lock:
            if self._pool.closed:
                self._pool.open(wait=False)

    def close(self) -> None:
        self._pool.close()

    def ping(self) -> bool:
        try:
            with self._connection() as connection:
                connection.execute("SELECT 1")
            return True
        except (psycopg.Error, PoolTimeout, RuntimeError):
            return False

    def get(self, task_id: str) -> TaskParameterRecord | None:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    """
                    SELECT task_id, worker_type, config, updated_at
                    FROM worker_task_parameters
                    WHERE task_id = %s
                    """,
                    (task_id,),
                ).fetchone()
        except (psycopg.Error, PoolTimeout) as error:
            raise RepositoryUnavailableError(
                "task parameter database is unavailable"
            ) from error
        if row is None:
            return None
        config = row["config"]
        if not isinstance(config, dict):
            raise RepositoryUnavailableError("stored task config is not a JSON object")
        return TaskParameterRecord(
            task_id=row["task_id"],
            worker_type=row["worker_type"],
            config=config,
            updated_at=row["updated_at"],
        )

    def upsert(
        self,
        task_id: str,
        worker_type: str,
        config: dict[str, Any],
    ) -> TaskParameterRecord:
        if not task_id.strip():
            raise ValueError("task_id must not be empty")
        if not worker_type.strip():
            raise ValueError("worker_type must not be empty")
        if not isinstance(config, dict):
            raise TypeError("config must be a JSON object")
        try:
            with self._connection() as connection:
                row = connection.execute(
                    """
                    INSERT INTO worker_task_parameters (task_id, worker_type, config)
                    VALUES (%s, %s, %s::jsonb)
                    ON CONFLICT (task_id) DO UPDATE
                    SET worker_type = EXCLUDED.worker_type,
                        config = EXCLUDED.config
                    RETURNING task_id, worker_type, config, updated_at
                    """,
                    (task_id, worker_type, psycopg.types.json.Jsonb(config)),
                ).fetchone()
        except (psycopg.Error, PoolTimeout) as error:
            raise RepositoryUnavailableError(
                "task parameter database is unavailable"
            ) from error
        assert row is not None
        return TaskParameterRecord(
            task_id=row["task_id"],
            worker_type=row["worker_type"],
            config=row["config"],
            updated_at=row["updated_at"],
        )

    def _connection(self):
        self.open()
        return self._pool.connection()
