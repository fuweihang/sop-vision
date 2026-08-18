"""守护进程的最小 RESTful 控制面。"""

from __future__ import annotations

import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, AsyncIterator, Callable

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status

from .config_loader import ConfigLoadError
from .manager import (
    WorkerBusyError,
    WorkerManager,
    WorkerNotFoundError,
    WorkerStartError,
    WorkerStartTimeout,
    WorkerStopError,
)
from .models import CommandResponse, HealthResponse


async def require_empty_body(request: Request) -> None:
    if (await request.body()).strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="worker command requests must have an empty body",
        )


EmptyBody = Annotated[None, Depends(require_empty_body)]


def create_app(
    config_path: Path | None = None,
    *,
    manager: WorkerManager | None = None,
) -> FastAPI:
    worker_manager = manager or WorkerManager(config_path or Path("config.json"))

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        worker_manager.close()

    app = FastAPI(
        title="SOP Vision Algorithm Daemon",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/healthz", response_model=HealthResponse)
    async def health(response: Response) -> HealthResponse:
        readable = await _run_blocking(worker_manager.config_is_readable)
        if not readable:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(
            status="ok" if readable else "degraded",
            config_readable=readable,
        )

    def command_route(
        path: str,
        operation: Callable[[str], CommandResponse],
    ) -> None:
        async def run(task_id: str, _empty: EmptyBody) -> CommandResponse:
            try:
                return await _run_blocking(operation, task_id)
            except ConfigLoadError as error:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="local config.json is invalid; see daemon logs",
                ) from error
            except WorkerNotFoundError as error:
                raise HTTPException(status_code=404, detail=str(error)) from error
            except WorkerBusyError as error:
                raise HTTPException(status_code=409, detail=str(error)) from error
            except WorkerStartTimeout as error:
                raise HTTPException(status_code=504, detail=str(error)) from error
            except WorkerStartError as error:
                raise HTTPException(status_code=500, detail=str(error)) from error
            except WorkerStopError as error:
                raise HTTPException(status_code=500, detail=str(error)) from error

        app.post(path, response_model=CommandResponse)(run)

    command_route("/v1/workers/{task_id}/start", worker_manager.start)
    command_route("/v1/workers/{task_id}/reload", worker_manager.reload)
    command_route("/v1/workers/{task_id}/restart", worker_manager.restart)
    command_route("/v1/workers/{task_id}/stop", worker_manager.stop)

    return app


async def _run_blocking(function: Callable[..., object], *args: object) -> object:
    """在线程中执行同步进程操作；命令低频，因此每次使用独立执行器。"""

    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="daemon-command")
    try:
        call = functools.partial(function, *args)
        return await asyncio.get_running_loop().run_in_executor(executor, call)
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
