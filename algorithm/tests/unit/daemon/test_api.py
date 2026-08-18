import asyncio

import httpx

from algorithm.daemon.api import create_app
from algorithm.daemon.models import CommandResponse


class FakeManager:
    def __init__(self) -> None:
        self.closed = False

    def config_is_readable(self) -> bool:
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
        )

    def start(self, task_id: str) -> CommandResponse:
        return self._response(task_id, "start")

    def reload(self, task_id: str) -> CommandResponse:
        return self._response(task_id, "reload")

    def restart(self, task_id: str) -> CommandResponse:
        return self._response(task_id, "restart")

    def stop(self, task_id: str) -> CommandResponse:
        return self._response(task_id, "stop")


def test_api_exposes_only_health_and_empty_body_commands() -> None:
    asyncio.run(_assert_api_exposes_only_health_and_commands())


async def _assert_api_exposes_only_health_and_commands() -> None:
    manager = FakeManager()
    app = create_app(manager=manager)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        health = await client.get("/healthz")
        started = await client.post("/v1/workers/task-1/start")

        assert health.json() == {"status": "ok", "config_readable": True}
        assert started.status_code == 200
        assert started.json()["runtime_state"] == "running"
        assert (await client.get("/v1/workers")).status_code == 404
        assert (await client.get("/openapi.json")).status_code == 404

    manager.close()
    assert manager.closed


def test_command_rejects_any_request_body() -> None:
    asyncio.run(_assert_command_rejects_any_request_body())


async def _assert_command_rejects_any_request_body() -> None:
    app = create_app(manager=FakeManager())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/workers/task-1/reload",
            json={"confidence": 0.8},
        )

    assert response.status_code == 422
    assert "empty body" in response.json()["detail"]
