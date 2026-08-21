from contextlib import contextmanager
from datetime import UTC, datetime

import psycopg

from algorithm.database import TaskParameterRepository


class FakeResult:
    def __init__(self, row=None) -> None:
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self) -> None:
        self.row = None
        self.statements = []

    def execute(self, statement, parameters=None):
        self.statements.append((statement, parameters))
        return FakeResult(self.row)


class FakePool:
    def __init__(self, connection) -> None:
        self.closed = False
        self.connection_value = connection

    def open(self, wait=False):
        self.closed = False

    def close(self):
        self.closed = True

    @contextmanager
    def connection(self):
        if isinstance(self.connection_value, Exception):
            raise self.connection_value
        yield self.connection_value


def repository_with(connection):
    repository = TaskParameterRepository("postgresql://unused")
    repository._pool = FakePool(connection)
    return repository


def test_repository_reads_and_upserts_task_records() -> None:
    connection = FakeConnection()
    updated_at = datetime(2026, 8, 21, tzinfo=UTC)
    connection.row = {
        "task_id": "task-1",
        "worker_type": "detector",
        "config": {"confidence": 0.5},
        "updated_at": updated_at,
    }
    repository = repository_with(connection)

    loaded = repository.get("task-1")
    saved = repository.upsert("task-1", "detector", {"confidence": 0.5})

    assert loaded is not None and loaded.task_id == "task-1"
    assert saved.updated_at == updated_at
    assert "SELECT task_id" in connection.statements[0][0]
    assert "ON CONFLICT" in connection.statements[1][0]


def test_repository_reports_unreachable_database_without_leaking_driver_error() -> None:
    repository = repository_with(psycopg.OperationalError("secret connection detail"))
    assert repository.ping() is False


def test_repository_rejects_empty_identifiers_before_writing() -> None:
    repository = repository_with(FakeConnection())
    try:
        repository.upsert(" ", "detector", {})
    except ValueError as error:
        assert "task_id" in str(error)
    else:
        raise AssertionError("empty task_id was accepted")
