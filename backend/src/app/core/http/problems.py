"""RFC 9457 风格的安全 Problem Details 模型与响应工厂。"""

from collections.abc import Mapping, Sequence
from http import HTTPStatus

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from app.core.http.middleware import TRACE_ID_HEADER
from app.core.http.trace import get_trace_id

PROBLEM_MEDIA_TYPE = "application/problem+json"
# Problem type 是标识符而不是 API 地址。项目目前没有长期受控域名，因此使用不依赖 DNS、
# IP 或部署环境的 URN 命名空间；具体 type 由稳定 code 推导，避免开发、测试、生产环境生成
# 不同标识，也避免调用者各自维护大小写或分隔符不同的变体。
PROBLEM_TYPE_URN_PREFIX = "urn:sop-vision:problem"


class FieldError(BaseModel):
    """一个可稳定映射到表单字段的公开校验错误。

    模型禁止额外字段并冻结实例，防止后续层临时附加原始输入，或在响应构造后无意修改错误
    code。``field`` 使用 ``sources[1].name`` 这类前端表单可消费的路径。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str
    code: str
    detail: str


class ProblemDetails(BaseModel):
    """所有结构化 HTTP 错误共享的唯一响应模型。

    ``context`` 只允许 JSON 值；调用工厂的映射代码仍需只放入已批准的非敏感字段，不能把
    原始异常、请求体或第三方响应整体塞入该字典。冻结和禁止额外字段也确保步骤 6 注册到
    OpenAPI 的模型与实际运行时响应保持同源。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: str
    title: str
    status: int = Field(ge=400, le=599)
    code: str
    detail: str
    instance: str
    trace_id: str
    errors: tuple[FieldError, ...] = ()
    context: dict[str, JsonValue] = Field(default_factory=dict)


def _trace_id_from_request(request: Request) -> str:
    """优先读取 middleware 写入的 request state，并兼容隔离 handler 单元测试。"""

    trace_id = getattr(request.state, "trace_id", None) or get_trace_id()
    # 正常应用中 middleware 一定先写入；fallback 只防止测试直接调用 handler 时产生空契约。
    return trace_id or "trace-unavailable"


def problem_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    title: str | None = None,
    detail: str | None = None,
    errors: Sequence[FieldError] = (),
    context: Mapping[str, JsonValue] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """构造不会包含 query string 或原始异常内容的 Problem JSON 响应。

    Args:
        request: 当前请求，用于读取同源 trace ID 和不含查询值的 path。
        status_code: 公开 HTTP 错误状态，必须处于 400-599。
        code: 供客户端分支使用的稳定业务或协议 code；工厂统一转为大写。
        title: 面向人的短标题；未提供时使用标准 HTTP reason phrase。
        detail: 安全、固定的错误说明；不能拼接用户输入或底层异常。
        errors: 已脱敏并定位到字段的错误集合。
        context: 经过调用方白名单审查的非敏感 JSON 上下文。
        headers: 需要保留的协议头，例如 ``WWW-Authenticate``。

    Returns:
        媒体类型固定为 ``application/problem+json``，且 header/body trace ID 一致的响应。

    Raises:
        pydantic.ValidationError: 调用方传入非法状态码或非 JSON context 时快速失败，避免生成
            不符合公共契约的响应。
    """

    try:
        phrase = HTTPStatus(status_code).phrase
    except ValueError:
        phrase = "HTTP Error"
    # 业务层即使传入大小写不同的 code，线上协议仍保持 Foundation 冻结的大写表示。
    normalized_code = code.upper()
    trace_id = _trace_id_from_request(request)
    problem = ProblemDetails(
        type=f"{PROBLEM_TYPE_URN_PREFIX}:{normalized_code.lower().replace('_', '-')}",
        title=title or phrase,
        status=status_code,
        code=normalized_code,
        detail=detail or "请求未能完成。",
        # query 可能包含搜索文本、凭据或其他敏感值，错误实例只能记录 path。
        instance=request.url.path,
        trace_id=trace_id,
        errors=tuple(errors),
        context=dict(context or {}),
    )
    # HTTPException 可携带 WWW-Authenticate 等协议头，但不能用其 Content-Type/Length 覆盖
    # 实际 Problem JSON，否则客户端会误判媒体类型或收到不匹配的长度。
    response_headers = {
        key: value
        for key, value in (headers or {}).items()
        if key.lower() not in {"content-length", "content-type"}
    }
    response_headers[TRACE_ID_HEADER] = trace_id
    return JSONResponse(
        status_code=status_code,
        content=problem.model_dump(mode="json"),
        headers=response_headers,
        media_type=PROBLEM_MEDIA_TYPE,
    )
