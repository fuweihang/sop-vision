from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import MediaMTXClientDependency
from app.schemas.health import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
async def readiness(client: MediaMTXClientDependency) -> HealthResponse:
    if not await client.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MediaMTX Control API is unavailable",
        )
    return HealthResponse(status="ok")
