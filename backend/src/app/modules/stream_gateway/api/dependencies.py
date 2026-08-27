from typing import Annotated

from fastapi import Depends, Request

from app.modules.stream_gateway.ports import StreamGatewayPort


def get_stream_gateway(request: Request) -> StreamGatewayPort:
    """返回框架无关 Port，禁止业务 handler 接触具体 HTTP Client。"""

    return request.app.state.stream_gateway


StreamGatewayDependency = Annotated[StreamGatewayPort, Depends(get_stream_gateway)]
