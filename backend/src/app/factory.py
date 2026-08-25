"""FastAPI 应用工厂：组装路由、中间件与进程级资源生命周期。"""

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.core.config import Settings, get_settings
from app.core.database import DatabaseRuntime, create_database_runtime
from app.core.http import (
    TraceIdMiddleware,
    install_http_exception_handlers,
    install_problem_openapi_media_type,
)
from app.modules.cameras.api.error_handlers import install_camera_exception_handlers
from app.modules.cameras.api.router import router as cameras_router
from app.modules.stream_gateway.api.router import router as stream_gateway_router
from app.modules.stream_gateway.services.mediamtx import MediaMTXClient

DatabaseRuntimeFactory = Callable[[Settings], DatabaseRuntime]
# FastAPI lifespan 接收应用实例，并返回由框架进入/退出的异步上下文管理器。
AppLifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def create_lifespan(
    settings: Settings,
    database_runtime_factory: DatabaseRuntimeFactory,
) -> AppLifespan:
    """创建绑定本次应用配置和数据库工厂的 lifespan。

    ``AsyncExitStack`` 按后进先出关闭资源，而且即使一个关闭回调抛错仍会继续执行其余
    回调。这样 MediaMTX client 与数据库连接池不会因另一个资源清理失败而泄漏。工厂
    参数也让测试可以注入隔离 Runtime，无需改写进程全局单例。
    """

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
        async with AsyncExitStack() as stack:
            # Engine/Session factory 只在进入 lifespan 时创建；模块导入和 OpenAPI 导出都不会
            # 创建连接池或连接数据库。
            database_runtime = database_runtime_factory(settings)
            stack.push_async_callback(database_runtime.dispose)
            application.state.database_runtime = database_runtime

            # MediaMTX 客户端复用现有应用级生命周期，并在数据库 Runtime 之前关闭。
            client = MediaMTXClient(
                base_url=settings.mediamtx_api_url,
                timeout=settings.mediamtx_api_timeout,
            )
            stack.push_async_callback(client.close)
            application.state.stream_gateway_mediamtx_client = client
            yield

    return lifespan


def create_app(
    settings: Settings | None = None,
    database_runtime_factory: DatabaseRuntimeFactory = create_database_runtime,
) -> FastAPI:
    """创建可独立测试的应用实例；未注入配置时使用缓存的进程环境配置。"""

    if settings is None:
        settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=create_lifespan(settings, database_runtime_factory),
    )
    # CORS 先注册、Trace 后注册是有意的：Starlette 后添加的 middleware 位于更外层。若顺序
    # 反过来，CORSMiddleware 可直接返回 OPTIONS 预检响应，Trace 将没有机会补充关联 ID。
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.backend_cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Starlette 后添加的 middleware 位于更外层；Trace 必须包住 CORS，确保预检等提前响应也
    # 带有请求关联 ID，并让成功、框架错误和领域错误使用同一个值。
    application.add_middleware(TraceIdMiddleware)
    # 框架异常与 Cameras 已知异常分开注册，保持 core 不反向依赖业务模块；二者最终都使用
    # 同一个 Problem 工厂，所以媒体类型、trace 和脱敏规则不会分叉。
    install_http_exception_handlers(application)
    install_camera_exception_handlers(application)
    application.include_router(stream_gateway_router)
    # Cameras 的业务 handler 仍是 Foundation 占位，但必须注册到真实应用，保证应用自身
    # /openapi.json、导出产物和未来运行时只共享一棵路由树。
    application.include_router(cameras_router, prefix="/api/v1")
    install_problem_openapi_media_type(application)
    return application
