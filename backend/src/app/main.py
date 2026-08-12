from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.core.config import get_settings
from app.modules.stream_gateway.api.router import router as stream_gateway_router
from app.modules.stream_gateway.services.mediamtx import MediaMTXClient


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    client = MediaMTXClient(
        base_url=settings.mediamtx_api_url,
        timeout=settings.mediamtx_api_timeout,
    )
    application.state.stream_gateway_mediamtx_client = client
    try:
        yield
    finally:
        await client.close()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.backend_cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(stream_gateway_router)
    return application


app = create_app()
