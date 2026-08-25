from fastapi import APIRouter

from app.modules.stream_gateway.api import health

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
