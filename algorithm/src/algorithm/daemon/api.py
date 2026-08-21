"""守护进程的最小 RESTful 控制面。"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import AsyncIterator, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status

from algorithm.common.config import project_root
from algorithm.database import RepositoryUnavailableError, TaskParameterRepository

from .configuration import WorkerConfigurationError
from .manager import (
    WorkerAlreadyRunningError,
    WorkerBusyError,
    WorkerManager,
    WorkerNotFoundError,
    WorkerPoolFullError,
    WorkerStartError,
    WorkerStartTimeout,
    WorkerStopError,
)
from .models import (
    CommandResponse,
    HealthResponse,
    WorkerTypeListResponse,
    WorkerTypeSummary,
)
from .registry import get_worker_definition, worker_type_names

DEFAULT_DATABASE_URL = "postgresql://sop_vision:sop_vision@localhost:5432/sop_vision"


async def require_empty_body(request: Request) -> None:
    if (await request.body()).strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="worker command requests must have an empty body",
        )


EmptyBody = Annotated[None, Depends(require_empty_body)]


def create_app(
    *,
    manager: WorkerManager | None = None,
    database_url: str = DEFAULT_DATABASE_URL,
    resource_root: Path | None = None,
    max_workers: int = 4,
) -> FastAPI:
    worker_manager = manager or WorkerManager(
        TaskParameterRepository(database_url),
        resource_root or project_root(),
        max_workers=max_workers,
    )

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
        reachable = await _run_blocking(worker_manager.database_is_reachable)
        if not reachable:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(
            status="ok" if reachable else "degraded",
            database_reachable=reachable,
            active_workers=worker_manager.active_workers,
            max_workers=worker_manager.max_workers,
        )

    @app.get("/v1/worker-types", response_model=WorkerTypeListResponse)
    async def list_worker_types() -> WorkerTypeListResponse:
        return WorkerTypeListResponse(
            worker_types=tuple(
                WorkerTypeSummary(
                    worker_type=worker_type,
                    schema_url=f"/v1/worker-types/{worker_type}/schema",
                )
                for worker_type in worker_type_names()
            )
        )

    @app.get("/v1/worker-types/{worker_type}/schema")
    async def worker_type_schema(worker_type: str) -> dict[str, Any]:
        try:
            return get_worker_definition(worker_type).parameter_schema()
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    def command_route(
        path: str,
        operation: Callable[[str], CommandResponse],
    ) -> None:
        async def run(task_id: str, _empty: EmptyBody) -> CommandResponse:
            try:
                return await _run_blocking(operation, task_id)
            except WorkerConfigurationError as error:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"stored worker configuration is invalid: {error}",
                ) from error
            except RepositoryUnavailableError as error:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="task parameter database is unavailable",
                ) from error
            except WorkerNotFoundError as error:
                raise HTTPException(status_code=404, detail=str(error)) from error
            except (WorkerBusyError, WorkerAlreadyRunningError) as error:
                raise HTTPException(status_code=409, detail=str(error)) from error
            except WorkerPoolFullError as error:
                raise HTTPException(status_code=429, detail=str(error)) from error
            except WorkerStartTimeout as error:
                raise HTTPException(status_code=504, detail=str(error)) from error
            except WorkerStartError as error:
                raise HTTPException(status_code=500, detail=str(error)) from error
            except WorkerStopError as error:
                raise HTTPException(status_code=500, detail=str(error)) from error

        app.post(path, response_model=CommandResponse)(run)

    command_route("/v1/workers/{task_id}/start", worker_manager.start)
    command_route("/v1/workers/{task_id}/reload", worker_manager.reload)
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
