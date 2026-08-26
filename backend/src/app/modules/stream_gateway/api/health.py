from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.database.session import DatabaseRuntime, get_database_runtime
from app.core.http import problem_responses, success_response
from app.modules.stream_gateway.schemas.health import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get(
    "/live",
    operation_id="healthLiveness",
    response_model=HealthResponse,
    responses={200: success_response("服务进程存活。", example={"status": "ok"})},
)
async def liveness() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get(
    "/ready",
    operation_id="healthReadiness",
    response_model=HealthResponse,
    responses={
        200: success_response("服务和数据库已经就绪。", example={"status": "ok"}),
        **problem_responses([status.HTTP_503_SERVICE_UNAVAILABLE]),
    },
)
async def readiness(
    runtime: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
) -> HealthResponse:
    """只检查配置读写必需的数据库；MediaMTX 故障由媒体投影独立表达。"""

    if not await runtime.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL 不可用",
        )
    return HealthResponse(status="ok")
