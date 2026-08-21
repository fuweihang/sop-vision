from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest
from alembic.config import Config

from alembic import command
from algorithm.database import TaskParameterRepository

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="set TEST_DATABASE_URL to run PostgreSQL integration tests",
)


def test_migration_constraints_upsert_and_updated_at(monkeypatch) -> None:
    assert DATABASE_URL is not None
    algorithm_root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("ALGORITHM_DATABASE_URL", DATABASE_URL)
    configuration = Config(str(algorithm_root / "alembic.ini"))

    command.downgrade(configuration, "base")
    command.upgrade(configuration, "head")
    command.upgrade(configuration, "head")

    repository = TaskParameterRepository(DATABASE_URL)
    try:
        first = repository.upsert("integration-task", "detector", {"confidence": 0.5})
        second = repository.upsert("integration-task", "detector", {"confidence": 0.7})
        assert second.updated_at > first.updated_at
        assert repository.get("integration-task").config["confidence"] == 0.7
    finally:
        repository.close()

    with (
        psycopg.connect(DATABASE_URL) as connection,
        pytest.raises(psycopg.errors.CheckViolation),
    ):
        connection.execute(
            """
            INSERT INTO worker_task_parameters (task_id, worker_type, config)
            VALUES ('invalid-json-shape', 'detector', '[]'::jsonb)
            """
        )
    command.downgrade(configuration, "base")
    command.upgrade(configuration, "head")
