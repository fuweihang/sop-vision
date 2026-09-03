"""Backend 测试共用的隔离 Settings、FastAPI 应用和 ASGI client。"""

import asyncio
import os
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr

# 普通测试不应依赖调用者是否预先加载了环境文件，因此显式构造 Settings 时统一使用
# 这条确定性的本地连接串。大多数测试只创建惰性 Engine，并不会真正连接该数据库。
UNIT_TEST_DATABASE_URL = "postgresql+psycopg://sop_vision:sop_vision@127.0.0.1:5432/sop_vision"

# app.main 在模块导入时创建生产入口，因此必须在下方导入应用模块前准备合法 URL。
# Engine 创建是惰性的，不使用数据库的测试不会访问本机 PostgreSQL；会变更数据库结构的
# integration 测试仍只能读取显式 TEST_DATABASE_URL，不能回退到这个应用库地址。
os.environ.setdefault("DATABASE_URL", UNIT_TEST_DATABASE_URL)

from app.core.config import Settings  # noqa: E402
from app.core.database import DatabaseRuntime  # noqa: E402
from app.factory import ReconciliationTaskRunner  # noqa: E402
from app.main import create_app  # noqa: E402
from app.modules.stream_gateway.ports import StreamGatewayPort  # noqa: E402


class ControlledTestReconciliationRunner:
    """普通 API 测试使用的可取消 Runner，不访问 PostgreSQL 或 MediaMTX。"""

    async def run_forever(self) -> None:
        """一直等待取消；使用 Event 可让应用关闭立即取消任务。"""

        await asyncio.Event().wait()


def create_controlled_test_reconciliation_runner(
    _settings: Settings,
    _database_runtime: DatabaseRuntime,
    _stream_gateway: StreamGatewayPort,
) -> ReconciliationTaskRunner:
    """创建不访问进程外资源的 Runner，供需要自行组装应用的测试复用。"""

    return ControlledTestReconciliationRunner()


@pytest.fixture
def anyio_backend() -> str:
    """统一异步测试后端，避免 AnyIO 额外参数化到未支持的运行时。"""

    return "asyncio"


@pytest.fixture
def settings() -> Settings:
    """提供不依赖进程环境的确定性配置。"""

    # Pydantic 运行时能把 str 转为 SecretStr，但静态检查器只接受字段声明的 SecretStr；
    # 显式包装同时保留类型和敏感值脱敏行为。
    return Settings(
        database_url=SecretStr(UNIT_TEST_DATABASE_URL),
        backend_cors_origins=["http://localhost:8000"],
    )


@pytest.fixture
def application(settings: Settings) -> FastAPI:
    """每个测试创建独立应用，隔离 app.state 与 dependency_overrides。"""

    return create_app(
        settings=settings,
        media_reconciliation_runner_factory=create_controlled_test_reconciliation_runner,
    )


@pytest.fixture
async def client(application: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """在完整 lifespan 内提供进程内 HTTP client，并在退出后清理覆盖。"""

    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client
    # 部分模块会按用例安装 FastAPI dependency override；统一清理可以防止共享应用时
    # 失败用例留下的覆盖影响后续测试。
    application.dependency_overrides.clear()
