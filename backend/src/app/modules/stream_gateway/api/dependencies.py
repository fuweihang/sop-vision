from typing import Annotated

from fastapi import Depends, Request

from app.modules.stream_gateway.services.mediamtx import MediaMTXClient


async def get_mediamtx_client(request: Request) -> MediaMTXClient:
    return request.app.state.stream_gateway_mediamtx_client


MediaMTXClientDependency = Annotated[MediaMTXClient, Depends(get_mediamtx_client)]
