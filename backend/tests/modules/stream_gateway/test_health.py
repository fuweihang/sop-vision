import httpx
import pytest
from fastapi import FastAPI

from app.modules.stream_gateway.api.dependencies import get_mediamtx_client

pytestmark = pytest.mark.anyio


class StubMediaMTXClient:
    def __init__(self, ready: bool) -> None:
        self._ready = ready

    async def is_ready(self) -> bool:
        return self._ready


async def test_liveness(client: httpx.AsyncClient) -> None:
    """数据库 Runtime 的加入不改变现有存活检查契约。"""

    response = await client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_when_mediamtx_is_available(
    client: httpx.AsyncClient,
    application: FastAPI,
) -> None:
    """独立应用实例上的依赖覆盖可模拟 MediaMTX 就绪。"""

    async def override_client() -> StubMediaMTXClient:
        return StubMediaMTXClient(ready=True)

    application.dependency_overrides[get_mediamtx_client] = override_client

    response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_when_mediamtx_is_unavailable(
    client: httpx.AsyncClient,
    application: FastAPI,
) -> None:
    """MediaMTX 不可用时仍保持既有 503 响应契约。"""

    async def override_client() -> StubMediaMTXClient:
        return StubMediaMTXClient(ready=False)

    application.dependency_overrides[get_mediamtx_client] = override_client

    response = await client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "MediaMTX Control API 不可用"}
