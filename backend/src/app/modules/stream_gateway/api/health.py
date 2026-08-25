from fastapi import APIRouter, HTTPException, status

from app.core.http import problem_responses, success_response
from app.modules.stream_gateway.api.dependencies import MediaMTXClientDependency
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
        200: success_response("服务依赖已经就绪。", example={"status": "ok"}),
        **problem_responses([status.HTTP_503_SERVICE_UNAVAILABLE]),
    },
)
async def readiness(client: MediaMTXClientDependency) -> HealthResponse:
    if not await client.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MediaMTX Control API 不可用",
        )
    return HealthResponse(status="ok")
