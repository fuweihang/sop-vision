import httpx
import pytest

from app.main import app
from app.modules.stream_gateway.api.dependencies import get_mediamtx_client

pytestmark = pytest.mark.anyio


class StubMediaMTXClient:
    def __init__(self, ready: bool) -> None:
        self._ready = ready

    async def is_ready(self) -> bool:
        return self._ready


async def test_liveness(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_when_mediamtx_is_available(client: httpx.AsyncClient) -> None:
    async def override_client() -> StubMediaMTXClient:
        return StubMediaMTXClient(ready=True)

    app.dependency_overrides[get_mediamtx_client] = override_client

    response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_when_mediamtx_is_unavailable(client: httpx.AsyncClient) -> None:
    async def override_client() -> StubMediaMTXClient:
        return StubMediaMTXClient(ready=False)

    app.dependency_overrides[get_mediamtx_client] = override_client

    response = await client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "MediaMTX Control API is unavailable"}
