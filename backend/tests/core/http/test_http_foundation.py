"""步骤 5 HTTP 公共机制的隔离 probe router 契约测试。

Foundation 明确禁止新增 Camera CRUD handler，因此本文件使用不进入生产应用、不进入 OpenAPI
的测试路由触发框架行为。这样既能覆盖 FastAPI 的真实参数解析与异常链，又不会让尚未实现的
业务路径看起来已经可调用。
"""

import logging
from collections.abc import AsyncIterator
from uuid import UUID

import httpx
import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import Settings
from app.core.http import CanonicalUUID4, TraceIdLogFilter, get_trace_id
from app.main import create_app
from app.modules.cameras.api.dependencies import (
    CameraListParameters,
    CameraListParametersDependency,
)
from app.modules.cameras.application.errors import CameraPersistenceOperationError
from app.modules.cameras.domain import (
    CameraDomainErrorCode,
    CameraFieldError,
    CameraValidationError,
)

pytestmark = pytest.mark.anyio

# UUID 同时包含字母和数字，才能可靠验证大写文本确实被拒绝；全数字 UUID 的 upper() 不会
# 改变字符串，无法覆盖 canonical 大小写规则。
CANONICAL_UUID4 = "8f14e45f-ea9d-4a7d-9b6d-8c9f0a1b2c3d"
# 两个唯一 sentinel 用于证明 Pydantic、异常链、响应和捕获日志都不会回显秘密或完整 RTSP URL。
LEAK_SENTINEL = "foundation-leak-sentinel"
RTSP_LEAK_SENTINEL = f"rtsp://admin:{LEAK_SENTINEL}@192.0.2.1:554/live"


class ProbeSource(BaseModel):
    """只存在于测试中的嵌套请求，用于验证字段路径和未知字段转换。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=8)
    url_suffix: str = Field(min_length=1, max_length=8)


class ProbeBody(BaseModel):
    """该模型不是 Camera 业务 DTO，不会进入生产 OpenAPI 或后续 Schema 来源。"""

    model_config = ConfigDict(extra="forbid")

    sources: list[ProbeSource] = Field(min_length=1)


class ProbeUuidBody(BaseModel):
    """证明同一严格 UUID 类型可用于请求体，而不只适用于路径参数。"""

    camera_id: CanonicalUUID4


# include_in_schema=False 是退出条件的一部分：探针只验证公共机制，不能污染步骤 6 将生成的
# 生产 OpenAPI，更不能冒充已交付的 Camera 业务端点。
probe_router = APIRouter(prefix="/_http-foundation-probe", include_in_schema=False)


@probe_router.get("/success")
async def probe_success() -> dict[str, str | None]:
    """同时证明业务读取和日志 Filter 读取的是 middleware 创建的同一个 ID。"""

    record = logging.LogRecord("probe", logging.INFO, __file__, 1, "probe", (), None)
    TraceIdLogFilter().filter(record)
    return {
        "request_trace_id": get_trace_id(),
        "log_trace_id": getattr(record, "trace_id", None),
    }


@probe_router.get("/uuid/{camera_id}")
async def probe_uuid(camera_id: CanonicalUUID4) -> dict[str, str]:
    """通过真实 Path 参数解析链验证严格 UUID 类型。"""

    return {"camera_id": str(camera_id)}


@probe_router.post("/uuid")
async def probe_body_uuid(body: ProbeUuidBody) -> dict[str, str]:
    """证明 Body 字段与 Path 参数复用同一 canonical UUID 规则。"""

    return {"camera_id": str(body.camera_id)}


@probe_router.get("/list")
async def probe_list(parameters: CameraListParametersDependency) -> dict[str, str | int | None]:
    """回显规范化参数及 Repository criteria，验证两层对象没有语义漂移。"""

    return {
        "page": parameters.page,
        "page_size": parameters.page_size,
        "q": parameters.q,
        "criteria_q": parameters.criteria.q,
    }


@probe_router.post("/body")
async def probe_body(body: ProbeBody) -> dict[str, int]:
    """触发嵌套列表和 extra 字段校验，不承载任何 Camera 业务行为。"""

    return {"source_count": len(body.sources)}


@probe_router.get("/domain-error")
async def probe_domain_error() -> None:
    """抛出只含稳定字段信息的领域错误，验证 Cameras HTTP 映射。"""

    raise CameraValidationError(
        CameraFieldError(
            field="sources[1].url_suffix",
            code=CameraDomainErrorCode.REQUIRED,
            detail="请输入视频源 URL 后缀。",
        )
    )


@probe_router.get("/database-error")
async def probe_database_error() -> None:
    """用含敏感异常链的依赖错误验证 503 脱敏边界。"""

    # 异常链故意包含秘密，证明 handler 不会把底层异常字符串复制进公开响应。
    raise CameraPersistenceOperationError() from RuntimeError(RTSP_LEAK_SENTINEL)


@probe_router.get("/http-error/{status_code}")
async def probe_http_error(status_code: int) -> None:
    """用故意含秘密的 detail 验证框架 HTTPException 不会原样公开。"""

    raise HTTPException(status_code=status_code, detail=RTSP_LEAK_SENTINEL)


@pytest.fixture
def probe_application(settings: Settings) -> FastAPI:
    """每例创建隔离应用；测试路由不会污染生产应用或 OpenAPI。"""

    application = create_app(settings=settings)
    application.include_router(probe_router)
    return application


@pytest.fixture
async def probe_client(probe_application: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """在完整 lifespan 内驱动 ASGI 应用，并在每例结束时释放进程级客户端。"""

    async with probe_application.router.lifespan_context(probe_application):
        transport = httpx.ASGITransport(app=probe_application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


async def test_success_response_uses_one_trace_id_for_header_context_and_logs(
    probe_client: httpx.AsyncClient,
) -> None:
    """成功响应的 header、请求 ContextVar 和日志字段必须使用同一个 trace ID。"""

    response = await probe_client.get("/_http-foundation-probe/success")

    assert response.status_code == 200
    trace_id = response.headers["x-trace-id"]
    assert response.json() == {
        "request_trace_id": trace_id,
        "log_trace_id": trace_id,
    }


async def test_valid_incoming_trace_id_is_forwarded(probe_client: httpx.AsyncClient) -> None:
    """符合入口白名单的上游 trace ID 应完整透传，支持跨服务关联。"""

    response = await probe_client.get(
        "/_http-foundation-probe/success",
        headers={"X-Trace-Id": "gateway.trace-123"},
    )

    assert response.headers["x-trace-id"] == "gateway.trace-123"
    assert response.json()["request_trace_id"] == "gateway.trace-123"


async def test_cors_preflight_response_also_has_trace_id(probe_client: httpx.AsyncClient) -> None:
    """CORS 提前返回的 OPTIONS 响应也必须经过外层 Trace 中间件。"""

    response = await probe_client.options(
        "/_http-foundation-probe/success",
        headers={
            "Origin": "http://localhost:8000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:8000"
    assert response.headers["x-trace-id"].startswith("tr_")


@pytest.mark.parametrize("incoming", ["contains spaces", "x" * 65, "bad/trace"])
async def test_untrusted_trace_id_text_is_replaced(
    probe_client: httpx.AsyncClient,
    incoming: str,
) -> None:
    """含空白、非法分隔符或超长的入口 ID 必须替换，不能进入响应和日志。"""

    response = await probe_client.get(
        "/_http-foundation-probe/success",
        headers={"X-Trace-Id": incoming},
    )

    replacement = response.headers["x-trace-id"]
    assert replacement != incoming
    assert replacement.startswith("tr_")


async def test_problem_trace_matches_header_and_instance_excludes_query(
    probe_client: httpx.AsyncClient,
) -> None:
    """Problem trace 必须与 header 一致，instance 只能包含不会泄密的 path。"""

    response = await probe_client.get(
        "/_http-foundation-probe/http-error/409?password=should-not-enter-instance"
    )

    problem = response.json()
    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    # type 使用与部署地址无关的稳定 URN；不能改成测试服务器 IP 或不存在的虚构域名。
    assert problem["type"] == "urn:sop-vision:problem:conflict"
    assert problem["trace_id"] == response.headers["x-trace-id"]
    assert problem["instance"] == "/_http-foundation-probe/http-error/409"
    assert "password" not in problem["instance"]
    assert RTSP_LEAK_SENTINEL not in response.text


@pytest.mark.parametrize(
    "uuid_text",
    [
        CANONICAL_UUID4.upper(),
        CANONICAL_UUID4.replace("-", ""),
        "{" + CANONICAL_UUID4 + "}",
        "00000000-0000-1000-8000-000000000001",
    ],
)
async def test_non_canonical_or_non_v4_uuid_returns_invalid_uuid(
    probe_client: httpx.AsyncClient,
    uuid_text: str,
) -> None:
    """宽松 UUID 解析器可接受的非标准文本也必须稳定返回 INVALID_UUID。"""

    response = await probe_client.get(f"/_http-foundation-probe/uuid/{uuid_text}")

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "urn:sop-vision:problem:validation-error"
    assert response.json()["errors"] == [
        {
            "field": "camera_id",
            "code": "INVALID_UUID",
            "detail": "请输入小写、带连字符的标准 UUID v4。",
        }
    ]


async def test_canonical_uuid4_is_parsed_as_uuid(probe_client: httpx.AsyncClient) -> None:
    """合法 canonical 文本在 handler 中应得到真实 UUID v4，而不是未校验字符串。"""

    response = await probe_client.get(f"/_http-foundation-probe/uuid/{CANONICAL_UUID4}")

    assert response.status_code == 200
    assert UUID(response.json()["camera_id"]).version == 4


async def test_request_body_uuid_uses_same_canonical_validation(
    probe_client: httpx.AsyncClient,
) -> None:
    """请求体 UUID 与路径 UUID 必须共享字段 code，避免不同入口出现两套契约。"""

    response = await probe_client.post(
        "/_http-foundation-probe/uuid",
        json={"camera_id": CANONICAL_UUID4.upper()},
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "camera_id"
    assert response.json()["errors"][0]["code"] == "INVALID_UUID"


async def test_nested_array_field_path_is_preserved(probe_client: httpx.AsyncClient) -> None:
    """Pydantic 数组 location 应精确转换为前端可定位的 sources[1] 路径。"""

    response = await probe_client.post(
        "/_http-foundation-probe/body",
        json={
            "sources": [
                {"name": "main", "url_suffix": "live"},
                {"name": "backup", "url_suffix": "too-long-value"},
            ]
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {
            "field": "sources[1].url_suffix",
            "code": "STRING_TOO_LONG",
            "detail": "该字段超过允许的最大长度。",
        }
    ]


async def test_unknown_json_field_does_not_echo_sensitive_input(
    probe_client: httpx.AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """未知字段只公开字段名和稳定 code，不得回显其密码或 RTSP URL 值。"""

    with caplog.at_level(logging.ERROR):
        response = await probe_client.post(
            "/_http-foundation-probe/body",
            json={
                "sources": [{"name": "main", "url_suffix": "live"}],
                "password": LEAK_SENTINEL,
                "rtsp_url": RTSP_LEAK_SENTINEL,
            },
        )

    assert response.status_code == 422
    assert [item["field"] for item in response.json()["errors"]] == ["password", "rtsp_url"]
    assert all(item["code"] == "UNKNOWN_FIELD" for item in response.json()["errors"])
    assert LEAK_SENTINEL not in response.text
    assert RTSP_LEAK_SENTINEL not in caplog.text


@pytest.mark.parametrize(
    ("query", "field"),
    [("page=0", "page"), ("page_size=101", "page_size"), (f"q={'x' * 101}", "q")],
)
async def test_invalid_list_parameter_has_precise_field(
    probe_client: httpx.AsyncClient,
    query: str,
    field: str,
) -> None:
    """分页和搜索边界失败必须指向具体 query 字段，而不是模糊的整体请求。"""

    response = await probe_client.get(f"/_http-foundation-probe/list?{query}")

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == field


async def test_list_parameters_normalize_blank_q_and_ignore_extra_query(
    probe_client: httpx.AsyncClient,
) -> None:
    """纯空白 q 收敛为 None，旧 sort 等额外参数不改变公共参数对象。"""

    response = await probe_client.get(
        "/_http-foundation-probe/list",
        params={"q": "   ", "page": "2", "page_size": "10", "sort": "name_desc"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "page": 2,
        "page_size": 10,
        "q": None,
        "criteria_q": None,
    }


async def test_list_parameters_are_immutable_values() -> None:
    """列表参数进入用例或 Query Key 后必须不可变，防止缓存键与实际查询分叉。"""

    parameters = CameraListParameters(page=1, page_size=20, q="lobby")

    with pytest.raises(ValidationError, match="frozen"):
        parameters.page = 2


async def test_non_blank_q_is_trimmed_before_length_check(probe_client: httpx.AsyncClient) -> None:
    """长度上限作用于 trim 后内容，边缘空白不应误伤恰好 100 字符的合法查询。"""

    response = await probe_client.get(
        "/_http-foundation-probe/list",
        params={"q": f"  {'x' * 100}  "},
    )

    assert response.status_code == 200
    assert response.json()["q"] == "x" * 100


async def test_domain_error_reuses_public_problem_model(probe_client: httpx.AsyncClient) -> None:
    """领域字段错误必须复用公共 Problem 媒体类型与字段形状。"""

    response = await probe_client.get("/_http-foundation-probe/domain-error")

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["errors"][0] == {
        "field": "sources[1].url_suffix",
        "code": "REQUIRED",
        "detail": "请输入视频源 URL 后缀。",
    }


async def test_known_database_error_is_safe_problem(
    probe_client: httpx.AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """已知数据库故障应返回 DATABASE_UNAVAILABLE，且异常链秘密不进入响应或日志。"""

    with caplog.at_level(logging.ERROR):
        response = await probe_client.get("/_http-foundation-probe/database-error")

    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_UNAVAILABLE"
    assert LEAK_SENTINEL not in response.text
    assert RTSP_LEAK_SENTINEL not in caplog.text


@pytest.mark.parametrize("status_code", [404, 409, 502, 503])
async def test_declared_http_errors_use_problem_media_type(
    probe_client: httpx.AsyncClient,
    status_code: int,
) -> None:
    """Foundation 预留的常见错误状态必须统一使用 Problem JSON，而非默认 detail。"""

    response = await probe_client.get(f"/_http-foundation-probe/http-error/{status_code}")

    assert response.status_code == status_code
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["status"] == status_code
