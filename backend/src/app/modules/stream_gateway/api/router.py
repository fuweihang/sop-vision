from fastapi import APIRouter

from app.modules.stream_gateway.api import cameras, health

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(cameras.router)
