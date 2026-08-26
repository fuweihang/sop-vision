"""公共 OpenAPI 响应声明与 Problem 媒体类型修正。"""

from collections.abc import Mapping, Sequence
from typing import Any

from fastapi import FastAPI

from app.core.http.middleware import TRACE_ID_HEADER
from app.core.http.problems import PROBLEM_MEDIA_TYPE, ProblemDetails

TRACE_HEADER_OPENAPI: dict[str, Any] = {
    "description": "本次请求的关联 ID；与 Problem body 的 trace_id 相同。",
    "schema": {"type": "string"},
}
_PROBLEM_CODES = {
    404: "NOT_FOUND",
    409: "PLAYBACK_NOT_AVAILABLE",
    422: "VALIDATION_ERROR",
    500: "INTERNAL_SERVER_ERROR",
    502: "MEDIA_SERVICE_INVALID_RESPONSE",
    503: "SERVICE_UNAVAILABLE",
}
_PROBLEM_TITLES = {
    404: "资源不存在",
    409: "播放尚不可用",
    422: "请求字段验证失败",
    500: "服务器内部错误",
    502: "媒体服务响应无效",
    503: "服务暂不可用",
}


def _problem_example(status_code: int) -> dict[str, Any]:
    """生成与响应状态一致且不含请求输入、凭据或基础设施细节的固定 Problem example。"""

    code = _PROBLEM_CODES[status_code]
    errors = []
    if status_code == 422:
        errors = [
            {
                "field": "sources[0].name",
                "code": "REQUIRED",
                "detail": "该字段为必填项。",
            }
        ]
    return {
        "type": f"urn:sop-vision:problem:{code.lower().replace('_', '-')}",
        "title": _PROBLEM_TITLES[status_code],
        "status": status_code,
        "code": code,
        "detail": "请求未能完成。",
        "instance": "/api/v1/cameras",
        "trace_id": "tr_openapi_example",
        "errors": errors,
        "context": {},
    }


def response_headers(*, location: bool = False, no_store: bool = False) -> dict[str, Any]:
    """构造每个响应都必须声明的 header，并按成功语义增加专用 header。"""

    headers: dict[str, Any] = {TRACE_ID_HEADER: TRACE_HEADER_OPENAPI}
    if location:
        headers["Location"] = {
            "description": "新建 Camera 的规范详情路径。",
            "schema": {"type": "string"},
        }
    if no_store:
        headers["Cache-Control"] = {
            "description": "该响应不得被浏览器或共享缓存持久化。",
            "schema": {"type": "string", "const": "no-store"},
        }
    return headers


def success_response(
    description: str,
    *,
    example: Mapping[str, Any] | None = None,
    location: bool = False,
    no_store: bool = False,
) -> dict[str, Any]:
    """为主要成功响应补充稳定描述、header 和经模型验证的固定 example。"""

    response: dict[str, Any] = {
        "description": description,
        "headers": response_headers(location=location, no_store=no_store),
    }
    if example is not None:
        response["content"] = {"application/json": {"example": dict(example)}}
    return response


def no_content_response(description: str) -> dict[str, Any]:
    """声明真正无 body 的 204；不添加会让客户端误判有 JSON 的 content。"""

    return {"description": description, "headers": response_headers()}


def problem_responses(
    statuses: Sequence[int],
    *,
    retry_after_statuses: Sequence[int] = (),
) -> dict[int, dict[str, Any]]:
    """生成引用公共 ProblemDetails 的错误响应集合。

    FastAPI 的 ``responses.model`` 会先按默认响应类生成 ``application/json``。这里同时声明
    正确媒体类型以注册公共模型，应用安装的 OpenAPI 修正器随后只移动 Schema 引用并删除
    错误的 JSON 媒体类型；运行时仍由 ``problem_response`` 直接返回 Problem JSON。
    """

    responses: dict[int, dict[str, Any]] = {}
    for status_code in statuses:
        headers = response_headers()
        if status_code in retry_after_statuses:
            headers["Retry-After"] = {
                "description": "建议客户端再次检查播放可用性的秒数。",
                "schema": {"type": "integer", "minimum": 0},
            }
        responses[status_code] = {
            "description": f"HTTP {status_code} Problem Details",
            "model": ProblemDetails,
            "headers": headers,
            "content": {PROBLEM_MEDIA_TYPE: {"example": _problem_example(status_code)}},
        }
    return responses


def install_problem_openapi_media_type(application: FastAPI) -> None:
    """让应用自身的 ``/openapi.json`` 与运行时 Problem 媒体类型一致。

    修正器包装 FastAPI 已有的缓存方法，不复制框架内部 OpenAPI 生成参数。它仅处理同时显式
    声明 Problem 媒体类型的响应，因此不会改写普通 JSON 成功响应或第三方路由。
    """

    generate_openapi = application.openapi

    def openapi_with_problem_media_type() -> dict[str, Any]:
        schema = generate_openapi()
        for path_item in schema.get("paths", {}).values():
            for operation in path_item.values():
                if not isinstance(operation, dict):
                    continue
                for response in operation.get("responses", {}).values():
                    content = response.get("content", {})
                    problem_content = content.get(PROBLEM_MEDIA_TYPE)
                    json_content = content.get("application/json")
                    if problem_content is None or json_content is None:
                        continue
                    # ``model`` 生成的 $ref 位于 application/json；移到真实运行时媒体类型下。
                    if "schema" in json_content:
                        problem_content["schema"] = json_content["schema"]
                    del content["application/json"]
        return schema

    application.openapi = openapi_with_problem_media_type
