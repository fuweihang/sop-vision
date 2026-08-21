import asyncio
from datetime import UTC, datetime

import httpx

from algorithm.daemon.api import create_app
from algorithm.daemon.configuration import WorkerConfigurationError
from algorithm.daemon.manager import WorkerAlreadyRunningError, WorkerPoolFullError
from algorithm.daemon.models import CommandResponse
from algorithm.database import RepositoryUnavailableError


class FakeManager:
    def __init__(self) -> None:
        self.closed = False
        self.active_workers = 1
        self.max_workers = 4

    def database_is_reachable(self) -> bool:
        return True

    def close(self) -> None:
        self.closed = True

    def _response(self, task_id: str, command: str) -> CommandResponse:
        return CommandResponse(
            task_id=task_id,
            command=command,
            runtime_state="stopped" if command == "stop" else "running",
            pid=None if command == "stop" else 123,
            config_revision="sha256:abc",
            config_updated_at=datetime(2026, 8, 21, tzinfo=UTC),
        )

    def start(self, task_id: str) -> CommandResponse:
        if task_id == "running":
            raise WorkerAlreadyRunningError("already running")
        if task_id == "full":
            raise WorkerPoolFullError("capacity exhausted")
        if task_id == "database-down":
            raise RepositoryUnavailableError("secret driver details")
        if task_id == "invalid":
            raise WorkerConfigurationError("confidence: must be less than 1")
        return self._response(task_id, "start")

    def reload(self, task_id: str) -> CommandResponse:
        return self._response(task_id, "reload")

    def stop(self, task_id: str) -> CommandResponse:
        return self._response(task_id, "stop")


def test_api_exposes_health_schema_and_database_backed_commands() -> None:
    asyncio.run(_assert_api_contract())


async def _assert_api_contract() -> None:
    manager = FakeManager()
    app = create_app(manager=manager)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/healthz")
        worker_types = await client.get("/v1/worker-types")
        schema = await client.get("/v1/worker-types/detector/schema")
        started = await client.post("/v1/workers/task-1/start")

        assert health.json() == {
            "status": "ok",
            "database_reachable": True,
            "active_workers": 1,
            "max_workers": 4,
        }
        assert worker_types.json()["worker_types"][0]["worker_type"] == "detector"
        assert "task_id" not in schema.json()["properties"]
        assert started.status_code == 200
        assert started.json()["config_updated_at"] == "2026-08-21T00:00:00Z"
        assert (await client.get("/v1/worker-types/missing/schema")).status_code == 404
        assert (await client.post("/v1/workers/task-1/restart")).status_code == 404
        assert (await client.get("/openapi.json")).status_code == 404

        assert (await client.post("/v1/workers/running/start")).status_code == 409
        assert (await client.post("/v1/workers/full/start")).status_code == 429
        unavailable = await client.post("/v1/workers/database-down/start")
        assert unavailable.status_code == 503
        assert "secret" not in unavailable.text
        invalid = await client.post("/v1/workers/invalid/start")
        assert invalid.status_code == 422
        assert "confidence" in invalid.text

    manager.close()
    assert manager.closed


def test_command_rejects_any_request_body() -> None:
    asyncio.run(_assert_command_rejects_any_request_body())


async def _assert_command_rejects_any_request_body() -> None:
    app = create_app(manager=FakeManager())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/workers/task-1/reload",
            json={"confidence": 0.8},
        )

    assert response.status_code == 422
    assert "empty body" in response.json()["detail"]


def test_health_is_degraded_when_database_is_unreachable() -> None:
    manager = FakeManager()
    manager.database_is_reachable = lambda: False
    app = create_app(manager=manager)

    async def request_health() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.get("/healthz")

    response = asyncio.run(request_health())
    assert response.status_code == 503
    assert response.json()["database_reachable"] is False
