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
    command.upgrade(configuration, "20260821_0001")
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            """
            INSERT INTO worker_task_parameters (task_id, worker_type, config)
            VALUES (
                'legacy-detector',
                'detector',
                '{
                    "camera_id": "camera-001",
                    "source_id": "source-001",
                    "algorithm_id": "yolo_object_detection",
                    "algorithm_version": "0.1.0",
                    "confidence": 0.5
                }'::jsonb
            )
            """
        )
    command.upgrade(configuration, "head")
    command.upgrade(configuration, "head")

    with psycopg.connect(DATABASE_URL) as connection:
        legacy_config = connection.execute(
            "SELECT config FROM worker_task_parameters WHERE task_id = %s",
            ("legacy-detector",),
        ).fetchone()[0]
    assert legacy_config == {"confidence": 0.5}

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
