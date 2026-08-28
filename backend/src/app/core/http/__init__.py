"""SOP Vision 的公共 HTTP 契约与请求上下文。

该包只提供跨业务模块共享的 HTTP 机制，不包含 Camera CRUD 等具体业务行为。集中导出常用
类型可以让后续路由复用同一套 trace、Problem 和 UUID 契约，避免从多个内部模块拼装出
略有差异的响应规则。
"""

from app.core.http.access import HttpAccessLogMiddleware
from app.core.http.errors import add_http_exception_handler, install_http_exception_handlers
from app.core.http.middleware import TraceIdMiddleware
from app.core.http.openapi import (
    install_problem_openapi_media_type,
    no_content_response,
    problem_responses,
    success_response,
)
from app.core.http.problems import FieldError, ProblemDetails, problem_response
from app.core.http.trace import TraceIdLogFilter, get_trace_id
from app.core.http.types import CanonicalUUID4

__all__ = [
    "CanonicalUUID4",
    "FieldError",
    "HttpAccessLogMiddleware",
    "ProblemDetails",
    "TraceIdLogFilter",
    "TraceIdMiddleware",
    "add_http_exception_handler",
    "get_trace_id",
    "install_http_exception_handlers",
    "install_problem_openapi_media_type",
    "no_content_response",
    "problem_responses",
    "problem_response",
    "success_response",
]
