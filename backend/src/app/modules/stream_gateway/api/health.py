from fastapi import APIRouter, HTTPException, status

from app.modules.stream_gateway.api.dependencies import MediaMTXClientDependency
from app.modules.stream_gateway.schemas.health import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
async def readiness(client: MediaMTXClientDependency) -> HealthResponse:
    if not await client.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MediaMTX Control API 不可用",
        )
    return HealthResponse(status="ok")
