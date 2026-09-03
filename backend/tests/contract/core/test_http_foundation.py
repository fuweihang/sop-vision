"""HTTP 公共机制的隔离 probe router 契约测试。

本文件使用不进入生产路由和 OpenAPI 的测试路由触发公共框架行为。这样既能覆盖 FastAPI 的真实
参数解析与异常链，也能让公共机制测试不依赖 Camera 业务 handler 的实现状态。
"""

import logging
from collections.abc import AsyncIterator, Iterator
from uuid import UUID

import httpx
import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse
from starlette.types import Message

from app.core.config import Settings
from app.core.http import (
    CanonicalUUID4,
    HttpAccessLogMiddleware,
    TraceIdLogFilter,
    TraceIdMiddleware,
    get_trace_id,
)
from app.core.logging import ConsoleFormatter, JsonFormatter
from app.main import create_app
from tests.support.application import create_controlled_test_reconciliation_runner

pytestmark = pytest.mark.anyio

# UUID 同时包含字母和数字，才能可靠验证大写文本确实被拒绝；全数字 UUID 的 upper() 不会
# 改变字符串，无法覆盖 canonical 大小写规则。
CANONICAL_UUID4 = "8f14e45f-ea9d-4a7d-9b6d-8c9f0a1b2c3d"
# Core 契约只需要识别内容是否泄漏，不应依赖某个领域模块提供测试常量。
LEAK_SENTINEL = "http-foundation-secret-sentinel"
RTSP_LEAK_SENTINEL = "rtsp://admin:http-foundation-secret@192.0.2.1:554/live"
ACCESS_LOGGER_NAME = "app.core.http.access"


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


# include_in_schema=False 是公共契约边界的一部分：探针只验证公共机制，不能污染正式生成的
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


@probe_router.post("/body")
async def probe_body(body: ProbeBody) -> dict[str, int]:
    """触发嵌套列表和 extra 字段校验，不承载任何 Camera 业务行为。"""

    return {"source_count": len(body.sources)}


@probe_router.get("/http-error/{status_code}")
async def probe_http_error(status_code: int) -> None:
    """用故意含秘密的 detail 验证框架 HTTPException 不会原样公开。"""

    raise HTTPException(status_code=status_code, detail=RTSP_LEAK_SENTINEL)


@probe_router.get("/unhandled-error")
async def probe_unhandled_error() -> None:
    """在响应头发送前抛错，用于验证 access 记录 500 后仍把异常交给 ServerError。"""

    raise RuntimeError(RTSP_LEAK_SENTINEL)


@probe_router.get("/stream")
async def probe_stream() -> StreamingResponse:
    """返回两段正常流，证明 access 必须等待最后一段正文发送后才记录完成。"""

    async def chunks() -> AsyncIterator[bytes]:
        yield b"first-"
        yield b"second"

    return StreamingResponse(chunks(), media_type="text/plain")


@pytest.fixture
def probe_application(settings: Settings) -> FastAPI:
    """每例创建隔离应用；测试路由不会污染生产应用或 OpenAPI。"""

    application = create_app(
        settings=settings,
        media_reconciliation_runner_factory=create_controlled_test_reconciliation_runner,
    )
    application.include_router(probe_router)
    return application


@pytest.fixture
async def probe_client(probe_application: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """在完整 lifespan 内驱动 ASGI 应用，并在每例结束时释放进程级客户端。"""

    async with probe_application.router.lifespan_context(probe_application):
        transport = httpx.ASGITransport(app=probe_application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


@pytest.fixture
def access_caplog(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    """让 pytest Handler 模拟生产 Handler 的 trace Filter，并捕获 INFO access 事件。"""

    trace_filter = TraceIdLogFilter()
    caplog.handler.addFilter(trace_filter)
    caplog.set_level(logging.INFO, logger=ACCESS_LOGGER_NAME)
    try:
        yield caplog
    finally:
        caplog.handler.removeFilter(trace_filter)


def access_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """只返回应用级 access 事件，排除同一请求内其他业务或框架日志。"""

    return [record for record in caplog.records if record.name == ACCESS_LOGGER_NAME]


def test_health_openapi_contract_is_stable(application: FastAPI) -> None:
    """健康检查的客户端方法名和 readiness 错误媒体类型属于 Core 公共契约。"""

    openapi = application.openapi()
    liveness = openapi["paths"]["/api/v1/health/live"]["get"]
    readiness = openapi["paths"]["/api/v1/health/ready"]["get"]
    assert liveness["operationId"] == "healthLiveness"
    assert readiness["operationId"] == "healthReadiness"
    assert set(readiness["responses"]["503"]["content"]) == {"application/problem+json"}


async def test_success_response_uses_one_trace_id_for_header_context_and_logs(
    probe_client: httpx.AsyncClient,
    access_caplog: pytest.LogCaptureFixture,
) -> None:
    """成功响应的 header、请求 ContextVar 和日志字段必须使用同一个 trace ID。"""

    response = await probe_client.get("/_http-foundation-probe/success")

    assert response.status_code == 200
    trace_id = response.headers["x-trace-id"]
    assert response.json() == {
        "request_trace_id": trace_id,
        "log_trace_id": trace_id,
    }
    records = access_records(access_caplog)
    assert len(records) == 1
    assert records[0].event == "http.request_completed"
    assert records[0].outcome == "completed"
    assert records[0].status_code == 200
    assert records[0].trace_id == trace_id


async def test_valid_incoming_trace_id_is_forwarded(probe_client: httpx.AsyncClient) -> None:
    """符合入口白名单的上游 trace ID 应完整透传，支持跨服务关联。"""

    response = await probe_client.get(
        "/_http-foundation-probe/success",
        headers={"X-Trace-Id": "gateway.trace-123"},
    )

    assert response.headers["x-trace-id"] == "gateway.trace-123"
    assert response.json()["request_trace_id"] == "gateway.trace-123"


async def test_cors_preflight_response_also_has_trace_id_and_one_access_log(
    probe_client: httpx.AsyncClient,
    access_caplog: pytest.LogCaptureFixture,
) -> None:
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
    records = access_records(access_caplog)
    assert len(records) == 1
    assert records[0].method == "OPTIONS"
    assert records[0].trace_id == response.headers["x-trace-id"]


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
    access_caplog: pytest.LogCaptureFixture,
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
    records = access_records(access_caplog)
    assert len(records) == 1
    assert records[0].path == "/_http-foundation-probe/http-error/409"
    assert records[0].status_code == 409
    assert records[0].outcome == "completed"
    assert records[0].trace_id == response.headers["x-trace-id"]


@pytest.mark.parametrize(
    ("status_code", "expected_level"),
    [(409, logging.INFO), (503, logging.ERROR)],
)
async def test_completed_problem_uses_status_based_level(
    probe_client: httpx.AsyncClient,
    access_caplog: pytest.LogCaptureFixture,
    status_code: int,
    expected_level: int,
) -> None:
    """完整发送的 4xx 保持 INFO，完整发送的 5xx 使用 ERROR，但都属于 completed。"""

    response = await probe_client.get(f"/_http-foundation-probe/http-error/{status_code}")

    assert response.status_code == status_code
    records = access_records(access_caplog)
    assert len(records) == 1
    assert records[0].levelno == expected_level
    assert records[0].outcome == "completed"
    assert records[0].status_code == status_code


async def test_normal_stream_logs_only_after_last_body(
    probe_client: httpx.AsyncClient,
    access_caplog: pytest.LogCaptureFixture,
) -> None:
    """正常流式响应完整发送两段正文后只记录一条 completed。"""

    response = await probe_client.get("/_http-foundation-probe/stream")

    assert response.status_code == 200
    assert response.content == b"first-second"
    records = access_records(access_caplog)
    assert len(records) == 1
    assert records[0].outcome == "completed"
    assert records[0].status_code == 200


async def test_unhandled_error_before_response_start_logs_failed_with_request_trace(
    probe_client: httpx.AsyncClient,
    access_caplog: pytest.LogCaptureFixture,
) -> None:
    """响应头前的未知异常记录 500/failed，随后仍由现有 ServerError 链抛给测试客户端。"""

    with pytest.raises(RuntimeError, match=RTSP_LEAK_SENTINEL):
        await probe_client.get(
            "/_http-foundation-probe/unhandled-error",
            headers={"X-Trace-Id": "gateway.unhandled-123"},
        )

    records = access_records(access_caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.ERROR
    assert records[0].message == "HTTP 请求处理失败"
    assert records[0].status_code == 500
    assert records[0].outcome == "failed"
    assert records[0].trace_id == "gateway.unhandled-123"
    assert RTSP_LEAK_SENTINEL not in ConsoleFormatter().format(records[0])
    assert RTSP_LEAK_SENTINEL not in JsonFormatter().format(records[0])


async def test_stream_interruption_keeps_sent_status_and_logs_once(
    access_caplog: pytest.LogCaptureFixture,
) -> None:
    """已经发送 200 后中断只能标记 response_interrupted，不能伪造为 500。"""

    async def interrupted_app(_scope, _receive, send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"partial", "more_body": True})
        raise RuntimeError(RTSP_LEAK_SENTINEL)

    clock_values = iter([10.0, 10.32])
    middleware = HttpAccessLogMiddleware(interrupted_app, clock=lambda: next(clock_values))
    sent_messages: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent_messages.append(message)

    with pytest.raises(RuntimeError, match=RTSP_LEAK_SENTINEL):
        await middleware(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/v1/export",
                "query_string": b"password=must-not-be-read",
            },
            receive,
            send,
        )

    assert [message["type"] for message in sent_messages] == [
        "http.response.start",
        "http.response.body",
    ]
    records = access_records(access_caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.ERROR
    assert records[0].message == "HTTP 响应发送中断"
    assert records[0].status_code == 200
    assert records[0].outcome == "response_interrupted"
    assert records[0].duration_ms == 320


async def test_exception_after_completed_body_does_not_duplicate_access_log(
    access_caplog: pytest.LogCaptureFixture,
) -> None:
    """正文已完成后的异常继续抛出，但不能把已记录的 completed 改写或再记录一次。"""

    async def completed_then_failed_app(_scope, _receive, send) -> None:
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})
        raise RuntimeError(RTSP_LEAK_SENTINEL)

    clock_values = iter([20.0, 20.012])
    middleware = HttpAccessLogMiddleware(
        completed_then_failed_app, clock=lambda: next(clock_values)
    )

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message: Message) -> None:
        return None

    with pytest.raises(RuntimeError, match=RTSP_LEAK_SENTINEL):
        await middleware(
            {"type": "http", "method": "DELETE", "path": "/resource"},
            receive,
            send,
        )

    records = access_records(access_caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.INFO
    assert records[0].status_code == 204
    assert records[0].outcome == "completed"
    assert records[0].duration_ms == 12


async def test_access_log_omits_query_and_escapes_path_controls(
    probe_client: httpx.AsyncClient,
    access_caplog: pytest.LogCaptureFixture,
) -> None:
    """URL query 不能进入事件，解码后的换行 path 也不能伪造第二行日志。"""

    await probe_client.get(
        "/_http-foundation-probe/not-found/%0Aforged",
        params={"password": RTSP_LEAK_SENTINEL},
    )

    records = access_records(access_caplog)
    assert len(records) == 1
    console = ConsoleFormatter().format(records[0])
    json_output = JsonFormatter().format(records[0])
    assert RTSP_LEAK_SENTINEL not in console
    assert RTSP_LEAK_SENTINEL not in json_output
    # console 每条记录只占一行；path 中解码出的换行必须仍然转义成可见文本，不能伪造第二行。
    assert len(console.splitlines()) == 1
    assert len(json_output.splitlines()) == 1


def test_application_middleware_order_keeps_trace_around_access_and_cors(
    probe_application: FastAPI,
) -> None:
    """Trace 最外、Access 居中、CORS 最内，确保预检日志也带请求 trace。"""

    assert [item.cls for item in probe_application.user_middleware] == [
        TraceIdMiddleware,
        HttpAccessLogMiddleware,
        CORSMiddleware,
    ]


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


@pytest.mark.sensitive_data
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
