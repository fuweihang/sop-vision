"""只记录脱敏路径和真实响应结果的应用级 HTTP access middleware。"""

import logging
import time
from collections.abc import Callable
from typing import Literal

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

HTTP_ACCESS_EVENT = "http.request_completed"
HEALTH_PROBE_PATHS = frozenset(
    {
        "/api/v1/health/live",
        "/api/v1/health/ready",
    }
)

type AccessOutcome = Literal["completed", "failed", "response_interrupted"]
type MonotonicClock = Callable[[], float]

_MESSAGE_BY_OUTCOME: dict[AccessOutcome, str] = {
    "completed": "HTTP 请求完成",
    "failed": "HTTP 请求处理失败",
    "response_interrupted": "HTTP 响应发送中断",
}


class HttpAccessLogMiddleware:
    """在 HTTP 请求结束或中断时写入最多一条应用级 access log。

    状态码表示已经发送给客户端的真实响应状态。只有响应头尚未发送就发生未处理异常时，
    才记录外层 ServerErrorMiddleware 将生成的 500。响应头已经发送后发生异常时保留原状态码，
    并通过 ``ERROR`` 级别与 ``response_interrupted`` 表示正文没有完整发送。

    请求级状态全部保存在 ``__call__`` 的局部变量中，不能放到 middleware 实例上；同一个实例
    会并发处理多个请求，实例字段会导致状态码、耗时或单次记录标记串用。
    """

    def __init__(self, app: ASGIApp, *, clock: MonotonicClock = time.monotonic) -> None:
        self.app = app
        self.clock = clock

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """原样透传非 HTTP scope，并在 HTTP 响应最终结束时记录结果。"""

        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started_at = self.clock()
        status_code: int | None = None
        access_logged = False

        def log_access(*, outcome: AccessOutcome, response_status: int) -> None:
            nonlocal access_logged
            if access_logged:
                return

            access_logged = True
            duration_ms = max(0, int((self.clock() - started_at) * 1000))
            path = scope["path"]

            # 部署探针通常每几秒调用一次。只有完整成功响应才静默；错误状态、处理失败和流式
            # 中断仍需记录，否则探针异常会在最需要排查时消失。
            if (
                path in HEALTH_PROBE_PATHS
                and outcome == "completed"
                and 200 <= response_status < 400
            ):
                return

            is_error = outcome != "completed" or response_status >= 500
            level = logging.ERROR if is_error else logging.INFO
            logger.log(
                level,
                _MESSAGE_BY_OUTCOME[outcome],
                extra={
                    "event": HTTP_ACCESS_EVENT,
                    "method": scope["method"],
                    # 只读取 ASGI 已解析的 path；query_string、header、body、客户端地址都不得
                    # 进入 LogRecord，避免凭据或用户输入被 access log 意外保存。
                    "path": path,
                    "status_code": response_status,
                    "outcome": outcome,
                    "duration_ms": duration_ms,
                },
            )

        async def send_with_access_log(message: Message) -> None:
            nonlocal status_code

            if message["type"] == "http.response.start":
                # 只有下游 send 成功返回，才把状态视为已经发出。若发送响应头本身失败，不能
                # 假装客户端已经收到了该状态码。
                await send(message)
                status_code = message["status"]
                return

            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                # 最后一个正文消息成功发送后才算 completed。StreamingResponse 中途抛错会走
                # 外层 except，并保留先前已经发送的真实响应状态。
                log_access(
                    outcome="completed",
                    response_status=status_code if status_code is not None else 500,
                )

        try:
            await self.app(scope, receive, send_with_access_log)
        except Exception:
            if not access_logged:
                if status_code is None:
                    log_access(outcome="failed", response_status=500)
                else:
                    log_access(outcome="response_interrupted", response_status=status_code)
            # Access middleware 只旁路观察请求，不能吞异常或自行生成响应。现有
            # ServerErrorMiddleware/Uvicorn 继续负责错误响应和异常诊断。
            raise
