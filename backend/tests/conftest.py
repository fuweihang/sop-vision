"""Backend 测试的隔离应用与 ASGI client fixtures。"""

import os
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

# app.main 在模块导入时创建生产入口，因此要先提供只用于构造 Engine 的合法测试 URL。
# Engine 创建是惰性的；不使用数据库的 API 测试不会因此访问本机 PostgreSQL。
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://sop_vision:test-password@127.0.0.1:5432/sop_vision",
)

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture
def anyio_backend() -> str:
    """统一异步测试后端，避免 AnyIO 额外参数化到未支持的运行时。"""

    return "asyncio"


@pytest.fixture
def application() -> FastAPI:
    """每个测试创建独立应用，隔离 app.state 与 dependency_overrides。"""

    return create_app(settings=Settings())


@pytest.fixture
async def client(application: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """在完整 lifespan 内提供进程内 HTTP client，并在退出后清理依赖覆盖。"""

    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client
    application.dependency_overrides.clear()
