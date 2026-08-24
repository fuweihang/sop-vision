"""FastAPI/Starlette 框架异常到公共 Problem Details 的集中转换。"""

from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.types import HTTPExceptionHandler

from app.core.http.problems import problem_response
from app.core.http.validation import convert_validation_errors

# Starlette HTTPException 只携带状态码和自由形态 detail。这里把常见状态码收敛成稳定 code，
# 前端便可按 code 分支，而不必比较可能调整或本地化的错误文案。
_HTTP_ERROR_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    502: "BAD_GATEWAY",
    503: "SERVICE_UNAVAILABLE",
}


type _TypedHTTPExceptionHandler[ErrorT: Exception] = Callable[
    [Request, ErrorT],
    Response | Awaitable[Response],
]


def add_http_exception_handler[ErrorT: Exception](
    application: FastAPI,
    exception_type: type[ErrorT],
    handler: _TypedHTTPExceptionHandler[ErrorT],
) -> None:
    """注册异常参数保持精确类型的 HTTP handler。

    Starlette 1.6.0 的 ``add_exception_handler`` 把 HTTP handler 第二参数统一声明成
    ``Exception``，没有用泛型表达异常注册类型与 handler 参数之间的对应关系。这会让
    Pyright/Pylance 因函数参数逆变而拒绝合法的具体异常 handler。Starlette 运行时会先按
    ``exception_type`` 匹配再调用 handler，因此只在这个框架适配边界执行一次类型转换，
    业务 handler 仍保留可检查的具体异常类型。

    Args:
        application: 尚未启动、需要安装异常映射的 FastAPI 应用。
        exception_type: Starlette 用于运行时匹配的异常类型。
        handler: 只处理该异常类型及其子类的 HTTP handler。
    """

    application.add_exception_handler(
        exception_type,
        cast(HTTPExceptionHandler, handler),
    )


async def request_validation_exception_handler(
    request: Request,
    error: RequestValidationError,
):
    """把 FastAPI 请求校验异常转换为脱敏的字段 Problem。

    Pydantic 错误对象可能保存密码、完整 RTSP URL 等原始输入，因此这里只读取错误类型和
    字段位置，不序列化 ``error.body``、``input``、``ctx`` 或默认 ``msg``。
    """

    return problem_response(
        request,
        status_code=422,
        code="VALIDATION_ERROR",
        title="请求字段验证失败",
        detail="存在一个或者多个无效字段。",
        errors=convert_validation_errors(error.errors()),
    )


async def http_exception_handler(request: Request, error: StarletteHTTPException):
    """统一框架 HTTP 错误，并避免把任意 ``detail`` 对象直接公开。

    FastAPI 的 HTTPException 允许 detail 是任意 JSON 值，第三方扩展也可能把底层响应放进
    其中。公共边界只保留状态码与安全协议头，正文使用固定文案，防止意外泄露基础设施细节。
    """

    # 未冻结专用 code 的罕见状态仍得到结构一致的 HTTP_ERROR，而不会退回 FastAPI 默认结构。
    code = _HTTP_ERROR_CODES.get(error.status_code, "HTTP_ERROR")
    try:
        title = HTTPStatus(error.status_code).phrase
    except ValueError:
        title = "HTTP Error"
    return problem_response(
        request,
        status_code=error.status_code,
        code=code,
        title=title,
        detail="请求未能完成。",
        # 例如 401 的 WWW-Authenticate 仍需保留；响应工厂会覆盖 trace header。
        headers=error.headers,
    )


async def unhandled_exception_handler(request: Request, _error: Exception):
    """提供最后一道 500 脱敏边界。

    原始异常继续由 Starlette/Uvicorn 的异常链用于服务端诊断；公开响应不调用 ``str(error)``，
    避免 SQL、凭据、堆栈或第三方原始响应进入 Problem body。
    """

    return problem_response(
        request,
        status_code=500,
        code="INTERNAL_SERVER_ERROR",
        title="服务器内部错误",
        detail="服务器暂时无法完成请求。",
    )


def install_http_exception_handlers(application: FastAPI) -> None:
    """在应用工厂集中注册框架异常处理器。

    每个通过 ``create_app`` 创建的隔离应用都会得到相同错误协议，避免测试应用、生产入口或
    后续子路由因漏装 handler 而重新暴露 FastAPI 默认 ``detail`` 数组。
    """

    add_http_exception_handler(
        application,
        RequestValidationError,
        request_validation_exception_handler,
    )
    add_http_exception_handler(application, StarletteHTTPException, http_exception_handler)
    add_http_exception_handler(application, Exception, unhandled_exception_handler)
