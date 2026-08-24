import httpx
import pytest
from fastapi import FastAPI

from app.modules.stream_gateway.api.dependencies import get_mediamtx_client

pytestmark = pytest.mark.anyio


class StubMediaMTXClient:
    """只实现 readiness 所需端口，避免健康检查测试访问真实 MediaMTX。"""

    def __init__(self, ready: bool) -> None:
        """保存本例期望的确定性就绪状态。"""

        self._ready = ready

    async def is_ready(self) -> bool:
        """返回预置状态，不执行网络请求。"""

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
        """覆盖请求依赖，证明成功分支与应用级真实客户端生命周期解耦。"""

        return StubMediaMTXClient(ready=True)

    application.dependency_overrides[get_mediamtx_client] = override_client

    response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_when_mediamtx_is_unavailable(
    client: httpx.AsyncClient,
    application: FastAPI,
) -> None:
    """MediaMTX 不可用时由公共 HTTP 边界返回统一 Problem 503。"""

    async def override_client() -> StubMediaMTXClient:
        """稳定触发 503，使测试只验证公共错误边界而不依赖网络故障时机。"""

        return StubMediaMTXClient(ready=False)

    application.dependency_overrides[get_mediamtx_client] = override_client

    response = await client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    problem = response.json()
    assert problem["type"] == "urn:sop-vision:problem:service-unavailable"
    assert problem["status"] == 503
    assert problem["code"] == "SERVICE_UNAVAILABLE"
    assert problem["instance"] == "/api/v1/health/ready"
    assert problem["trace_id"] == response.headers["x-trace-id"]
