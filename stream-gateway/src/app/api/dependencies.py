from typing import Annotated

from fastapi import Depends, Request

from app.services.mediamtx import MediaMTXClient


async def get_mediamtx_client(request: Request) -> MediaMTXClient:
    return request.app.state.mediamtx_client


MediaMTXClientDependency = Annotated[MediaMTXClient, Depends(get_mediamtx_client)]
