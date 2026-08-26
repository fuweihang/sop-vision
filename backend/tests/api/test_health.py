import httpx
import pytest
from fastapi import FastAPI

from app.core.database.session import get_database_runtime

pytestmark = pytest.mark.anyio


class StubDatabaseRuntime:
    """只实现 readiness 所需端口，避免 API 测试访问真实 PostgreSQL。"""

    def __init__(self, ready: bool) -> None:
        """保存本例期望的确定性就绪状态。"""

        self._ready = ready

    async def is_ready(self) -> bool:
        """返回预置状态，不执行网络请求。"""

        return self._ready


async def test_liveness(client: httpx.AsyncClient) -> None:
    """存活探针只表达应用进程可响应，不依赖数据库或 MediaMTX。"""

    response = await client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_when_database_is_available(
    client: httpx.AsyncClient,
    application: FastAPI,
) -> None:
    """数据库可用时 readiness 返回成功，不读取 MediaMTX 状态。"""

    def override_runtime() -> StubDatabaseRuntime:
        """覆盖数据库 Runtime，避免调用 fixture 中惰性 Engine。"""

        return StubDatabaseRuntime(ready=True)

    application.dependency_overrides[get_database_runtime] = override_runtime

    response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_when_database_is_unavailable(
    client: httpx.AsyncClient,
    application: FastAPI,
) -> None:
    """数据库不可用时由公共 HTTP 边界返回统一 Problem 503。"""

    def override_runtime() -> StubDatabaseRuntime:
        """稳定触发 503，使测试只验证公共错误边界。"""

        return StubDatabaseRuntime(ready=False)

    application.dependency_overrides[get_database_runtime] = override_runtime

    response = await client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    problem = response.json()
    assert problem["type"] == "urn:sop-vision:problem:service-unavailable"
    assert problem["status"] == 503
    assert problem["code"] == "SERVICE_UNAVAILABLE"
    assert problem["instance"] == "/api/v1/health/ready"
    assert problem["trace_id"] == response.headers["x-trace-id"]
