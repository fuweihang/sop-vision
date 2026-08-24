"""Backend 测试的隔离应用与 ASGI client fixtures。"""

import os
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr

# 普通单元测试不应依赖调用者是否预先加载了环境文件，因此显式构造 Settings 时统一使用
# 这条确定性的本地连接串。多数测试只创建惰性 Engine，并不会真正连接该数据库。
UNIT_TEST_DATABASE_URL = "postgresql+psycopg://sop_vision:sop_vision@127.0.0.1:5432/sop_vision"

# app.main 在模块导入时创建生产入口，因此要先提供只用于构造 Engine 的合法应用库 URL。
# 默认凭据与本地 Compose 保持一致，避免测试配置出现另一套无实际用途的账号或密码；
# Engine 创建是惰性的，不使用数据库的 API 测试不会因此访问本机 PostgreSQL。
# 会实际变更数据库结构的迁移测试必须另行提供指向 sop_vision_test 的 TEST_DATABASE_URL。
os.environ.setdefault("DATABASE_URL", UNIT_TEST_DATABASE_URL)

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture
def anyio_backend() -> str:
    """统一异步测试后端，避免 AnyIO 额外参数化到未支持的运行时。"""

    return "asyncio"


@pytest.fixture
def settings() -> Settings:
    """提供不依赖进程环境的确定性配置，避免普通测试触发动态构造签名误报。"""

    # Pydantic 运行时能把 str 转为 SecretStr，但静态检查器只接受字段声明的 SecretStr；
    # 测试显式包装输入，既保留敏感值语义，也避免用 ignore 掩盖真正的参数类型错误。
    return Settings(database_url=SecretStr(UNIT_TEST_DATABASE_URL))


@pytest.fixture
def application(settings: Settings) -> FastAPI:
    """每个测试创建独立应用，隔离 app.state 与 dependency_overrides。"""

    return create_app(settings=settings)


@pytest.fixture
async def client(application: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """在完整 lifespan 内提供进程内 HTTP client，并在退出后清理依赖覆盖。"""

    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client
    application.dependency_overrides.clear()
