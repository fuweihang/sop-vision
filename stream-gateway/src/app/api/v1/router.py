from fastapi import APIRouter

from app.api.v1 import cameras, health

router = APIRouter()
router.include_router(health.router)
router.include_router(cameras.router)
