"""FastAPI 应用工厂：组装路由、中间件与进程级资源生命周期。"""

import asyncio
import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from typing import Protocol

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.health import router as health_router
from app.core.config import Settings, get_settings
from app.core.database import DatabaseRuntime, create_database_runtime
from app.core.http import (
    TraceIdMiddleware,
    install_http_exception_handlers,
    install_problem_openapi_media_type,
)
from app.core.logging import safe_exception_fields
from app.modules.cameras.api.error_handlers import install_camera_exception_handlers
from app.modules.cameras.api.router import router as cameras_router
from app.modules.cameras.application.reconciliation import MediaReconciliationRunner
from app.modules.cameras.persistence.reconciliation import PostgreSQLMediaReconciliationLease
from app.modules.stream_gateway.ports import StreamGatewayPort
from app.modules.stream_gateway.services.mediamtx import MediaMTXAdapter

logger = logging.getLogger(__name__)
RECONCILIATION_SHUTDOWN_TIMEOUT_SECONDS = 5.0

DatabaseRuntimeFactory = Callable[[Settings], DatabaseRuntime]
# FastAPI lifespan 接收应用实例，并返回由框架进入/退出的异步上下文管理器。
AppLifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


class ReconciliationTaskRunner(Protocol):
    """应用工厂启动后台任务所需的窄接口，便于测试注入可控替身。"""

    async def run_forever(self) -> None: ...


MediaReconciliationRunnerFactory = Callable[
    [Settings, DatabaseRuntime, StreamGatewayPort],
    ReconciliationTaskRunner,
]


def create_media_reconciliation_runner(
    settings: Settings,
    database_runtime: DatabaseRuntime,
    stream_gateway: StreamGatewayPort,
) -> MediaReconciliationRunner:
    """使用当前应用的 Engine 与共享 MediaMTX Port 组装生产 Runner。"""

    return MediaReconciliationRunner(
        lease=PostgreSQLMediaReconciliationLease(database_runtime.engine),
        stream_gateway=stream_gateway,
        interval_seconds=settings.media_reconciliation_interval_seconds,
        max_backoff_seconds=settings.media_reconciliation_max_backoff_seconds,
    )


async def _stop_reconciliation_task(task: asyncio.Task[None]) -> None:
    """先取消 Runner 并最多等待 5 秒，之后 lifespan 才关闭它依赖的资源。"""

    task.cancel()
    try:
        async with asyncio.timeout(RECONCILIATION_SHUTDOWN_TIMEOUT_SECONDS):
            await task
    except asyncio.CancelledError:
        # 正常关闭时 Runner 应传播我们刚发出的取消；若是当前 shutdown 自身被取消，则继续
        # 向上传播，不能把服务器强制退出误当成后台任务已安全停止。
        if not task.cancelled():
            raise
    except TimeoutError:
        logger.error(
            "媒体对账任务停止异常",
            extra={
                "event": "media_reconciliation.runner_exit",
                "outcome": "shutdown_timeout",
                "timeout_seconds": RECONCILIATION_SHUTDOWN_TIMEOUT_SECONDS,
            },
        )
    except Exception as error:
        # helper 只返回异常类型和代码位置，不读取异常文本；不能改用 logger.exception()。
        logger.error(
            "媒体对账任务停止异常",
            extra={
                "event": "media_reconciliation.runner_exit",
                "outcome": "shutdown_error",
                **safe_exception_fields(error),
            },
        )


def _report_reconciliation_task_exit(task: asyncio.Task[None]) -> None:
    """报告非取消退出，防止后台任务在服务器继续运行时静默消失。"""

    if task.cancelled():
        return
    try:
        error = task.exception()
    except asyncio.CancelledError:
        return
    extra: dict[str, object] = {
        "event": "media_reconciliation.runner_exit",
        "outcome": "crashed" if error is not None else "unexpected_exit",
    }
    if error is not None:
        extra.update(safe_exception_fields(error))
    logger.error("媒体对账任务停止异常", extra=extra)


def create_lifespan(
    settings: Settings,
    database_runtime_factory: DatabaseRuntimeFactory,
    media_reconciliation_runner_factory: MediaReconciliationRunnerFactory,
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

            # Adapter 持有唯一的共享 HTTP Client，并以框架无关 Port 身份进入 app.state。
            # 后续 Cameras Service 只通过 dependency 获取 Port，不会接触 httpx 或具体实现。
            stream_gateway = MediaMTXAdapter(
                control_api_url=settings.mediamtx_api_url,
                request_timeout=settings.mediamtx_api_timeout,
                public_webrtc_base_url=settings.public_webrtc_base_url,
            )
            stack.push_async_callback(stream_gateway.close)
            application.state.stream_gateway = stream_gateway

            # create_task 后立即开放 API，首次对账在事件循环下一次调度中执行。停止回调最后
            # 注册、最先执行，确保 Runner 完全退出后才关闭 HTTP Client 和数据库连接池。
            reconciliation_runner = media_reconciliation_runner_factory(
                settings,
                database_runtime,
                stream_gateway,
            )
            reconciliation_task = asyncio.create_task(
                reconciliation_runner.run_forever(),
                name="media-reconciliation-runner",
            )
            # create_task 的异常不会自动传回 lifespan。done callback 只负责报告意外退出；正常
            # shutdown 仍由 ExitStack 中的停止回调取消并等待任务，避免出现两个清理入口。
            reconciliation_task.add_done_callback(_report_reconciliation_task_exit)
            stack.push_async_callback(_stop_reconciliation_task, reconciliation_task)
            application.state.media_reconciliation_runner = reconciliation_runner
            application.state.media_reconciliation_task = reconciliation_task
            yield

    return lifespan


def create_app(
    settings: Settings | None = None,
    database_runtime_factory: DatabaseRuntimeFactory = create_database_runtime,
    media_reconciliation_runner_factory: MediaReconciliationRunnerFactory = (
        create_media_reconciliation_runner
    ),
) -> FastAPI:
    """创建可独立测试的应用实例；未注入配置时使用缓存的进程环境配置。"""

    if settings is None:
        settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=create_lifespan(
            settings,
            database_runtime_factory,
            media_reconciliation_runner_factory,
        ),
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
    # 健康探针描述应用进程及其必要数据库依赖，不经由任何业务或外部服务适配模块注册。
    application.include_router(health_router, prefix="/api/v1")
    # Cameras handler 按功能切片逐个原位实现；尚未实现者继续保持 Foundation 纯占位。
    # 所有路径始终注册到真实应用，保证 /openapi.json、生成产物和运行时共享一棵路由树。
    application.include_router(cameras_router, prefix="/api/v1")
    install_problem_openapi_media_type(application)
    return application
