"""为全部 HTTP 响应建立同源 trace ID 的 ASGI 中间件。"""

import re
from collections.abc import MutableMapping
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.http.trace import bind_trace_id, reset_trace_id

TRACE_ID_HEADER = "X-Trace-Id"
# 入口 trace ID 允许常见网关分隔符，但禁止空白、斜杠、控制字符和超长文本，避免 header
# 注入、日志换行以及攻击者制造无界高基数字段。64 字符足够容纳主流 trace 格式。
_TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")


def _new_trace_id() -> str:
    """生成不携带时间、主机或业务含义的进程无关 trace ID。

    ``tr_`` 前缀便于日志中识别本服务生成的值；随机 UUID 不暴露部署拓扑，也不要求多个
    worker 共享计数器或锁。
    """

    return f"tr_{uuid4().hex}"


def _select_trace_id(headers: Headers, *, trust_incoming: bool) -> str:
    """选择本次请求唯一使用的 trace ID。

    只有 composition root 明确信任入口、且文本满足字符与长度白名单时才透传；其他情况
    生成新值。这样恶意输入不会原样进入响应或日志，同时合法网关 trace 可以跨服务关联。
    """

    incoming = headers.get(TRACE_ID_HEADER)
    if trust_incoming and incoming is not None and _TRACE_ID_PATTERN.fullmatch(incoming):
        return incoming
    return _new_trace_id()


class TraceIdMiddleware:
    """把单个 trace ID 注入 request state、ContextVar 和响应头。

    使用纯 ASGI 包装 ``http.response.start``，避免 ``BaseHTTPMiddleware`` 创建额外 task 后
    ContextVar 传播方向不直观。异常处理器生成的 Problem 自身也会写入相同响应头，因此即使
    未处理异常由 Starlette 最外层错误中间件接管，header/body 仍保持一致。
    """

    def __init__(self, app: ASGIApp, *, trust_incoming: bool = True) -> None:
        self.app = app
        # 部署入口必须确保上游代理清除客户端伪造值后，才应启用透传。当前单体入口把 HTTP
        # 调用方视作该入口的 trace 来源；未来接入网关时可在 composition root 关闭此选项。
        self.trust_incoming = trust_incoming

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """处理一次 ASGI 调用，并保证请求结束时清理 ContextVar。

        WebSocket、lifespan 等非 HTTP scope 不具有 HTTP 响应头语义，因此原样交给下游；HTTP
        scope 则在调用路由前写入 state/context，并在首个响应消息上覆盖 trace header。
        """

        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        trace_id = _select_trace_id(Headers(scope=scope), trust_incoming=self.trust_incoming)
        state = scope.setdefault("state", {})
        # Starlette 的 Scope 类型对 state 的具体映射类型描述较宽；运行时始终是可变字典。
        request_state = state if isinstance(state, MutableMapping) else {}
        request_state["trace_id"] = trace_id
        scope["state"] = request_state
        token = bind_trace_id(trace_id)

        async def send_with_trace_id(message: Message) -> None:
            # 只修改 response.start，确保成功响应、CORS 预检和流式响应都在正文发送前得到
            # header；后续 body 消息不能再安全修改已发出的响应头。
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[TRACE_ID_HEADER] = trace_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_trace_id)
        finally:
            # 即使路由取消或异常向外传播也必须 reset，否则同一 event loop 上的后续请求可能
            # 在日志中继承错误的 trace ID。
            reset_trace_id(token)
