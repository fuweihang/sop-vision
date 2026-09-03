"""Camera 创建 Router 的请求解析、响应 Header 和错误映射测试。"""

import logging
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from app.core.http.middleware import TRACE_ID_HEADER
from app.core.http.trace import TraceIdLogFilter
from app.modules.cameras.api.dependencies import (
    get_camera_clock,
    get_camera_id_generator,
    get_camera_unit_of_work,
)
from app.modules.cameras.application import CameraPersistenceOperationError
from app.modules.stream_gateway.api.dependencies import get_stream_gateway
from app.modules.stream_gateway.ports import (
    RuntimePath,
    RuntimePathSnapshot,
    StreamGatewayInvalidResponseError,
)
from tests.support.cameras.builders import FixedClock, FixedIdGenerator, uuid4_from_index
from tests.support.cameras.fakes import (
    FakeCameraStore,
    FakeCameraUnitOfWork,
    FakeStreamGateway,
)

pytestmark = pytest.mark.anyio

CREATED_AT = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)
SNAPSHOT_AT = datetime(2026, 8, 27, 8, 0, 1, tzinfo=UTC)
TEST_PASSWORD = "camera-create-api-password"


def request_body() -> dict:
    """返回可由各错误场景独立修改的双 Source 请求。"""

    return {
        "name": " 洗手区 01 ",
        "ip_address": "192.0.2.64",
        "rtsp_port": 554,
        "username": "operator name",
        "password": TEST_PASSWORD,
        "sources": [
            {
                "name": " 主码流 ",
                "url_suffix": " /Streaming/Channels/101 ",
                "is_default_preview": True,
            },
            {
                "name": " 子码流 ",
                "url_suffix": "/Streaming/Channels/102",
                "is_default_preview": False,
            },
        ],
    }


def install_create_overrides(
    application: FastAPI,
    *,
    uow: FakeCameraUnitOfWork,
    gateway: FakeStreamGateway,
) -> None:
    """覆盖全部进程外依赖，让 Router 测试不访问数据库或 MediaMTX。"""

    id_generator = FixedIdGenerator(uuid4_from_index(index) for index in range(1, 4))
    application.dependency_overrides[get_camera_unit_of_work] = lambda: uow
    application.dependency_overrides[get_stream_gateway] = lambda: gateway
    application.dependency_overrides[get_camera_id_generator] = lambda: id_generator
    application.dependency_overrides[get_camera_clock] = lambda: FixedClock(CREATED_AT)


async def test_创建接口解析请求并设置敏感响应头(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """POST 会规范化请求，并为包含凭据的 201 响应设置 Location 与 no-store。"""

    first_source_id = uuid4_from_index(2)
    gateway = FakeStreamGateway(
        RuntimePathSnapshot(
            paths=(RuntimePath(name=str(first_source_id), available=True, online=True),),
            checked_at=SNAPSHOT_AT,
        )
    )
    install_create_overrides(
        application,
        uow=FakeCameraUnitOfWork(FakeCameraStore()),
        gateway=gateway,
    )

    response = await client.post("/api/v1/cameras", json=request_body())

    assert response.status_code == 201
    assert response.headers["location"] == f"/api/v1/cameras/{uuid4_from_index(1)}"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers[TRACE_ID_HEADER]
    body = response.json()
    assert body["name"] == "洗手区 01"
    assert body["sources"][0]["url_suffix"] == "Streaming/Channels/101"
    assert body["sources"][0]["rtsp_url"] == (
        f"rtsp://operator%20name:{TEST_PASSWORD}@192.0.2.64:554/Streaming/Channels/101"
    )


async def test_创建接口用响应追踪ID关联降级日志(
    application: FastAPI,
    client: httpx.AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """提交后的媒体降级仍返回 201，且业务日志只用 Trace ID 关联请求。"""

    gateway = FakeStreamGateway(StreamGatewayInvalidResponseError())
    gateway.ensure_failures[uuid4_from_index(2)] = StreamGatewayInvalidResponseError()
    gateway.ensure_failures[uuid4_from_index(3)] = StreamGatewayInvalidResponseError()
    install_create_overrides(
        application,
        uow=FakeCameraUnitOfWork(FakeCameraStore()),
        gateway=gateway,
    )

    # 测试应用不运行 app.server 的日志配置；给 caplog 安装生产同款 Filter，才能验证中间件
    # 设置的 Trace ID 会进入业务日志，同时不会把请求密码作为关联信息写入日志。
    trace_filter = TraceIdLogFilter()
    caplog.handler.addFilter(trace_filter)
    try:
        with caplog.at_level(logging.WARNING, logger="app.modules.cameras.application.create"):
            response = await client.post("/api/v1/cameras", json=request_body())
    finally:
        caplog.handler.removeFilter(trace_filter)

    assert response.status_code == 201
    record = next(
        item
        for item in caplog.records
        if getattr(item, "event", None) == "camera.media_sync_degraded"
    )
    assert record.trace_id == response.headers[TRACE_ID_HEADER]
    assert TEST_PASSWORD not in caplog.text


@pytest.mark.sensitive_data
async def test_创建接口在视频源为空的问题详情中隐藏输入(
    client: httpx.AsyncClient,
) -> None:
    """空 Source 数组返回创建专用字段错误，但不回显同一请求内的密码。"""

    payload = request_body()
    payload["sources"] = []

    response = await client.post("/api/v1/cameras", json=payload)

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["errors"] == [
        {
            "field": "sources",
            "code": "SOURCE_REQUIRED",
            "detail": "Camera 至少需要一路 Source。",
        }
    ]
    assert TEST_PASSWORD not in response.text


@pytest.mark.sensitive_data
async def test_创建接口映射模型错误且不回显输入(
    client: httpx.AsyncClient,
) -> None:
    """非法 IPv4、端口和未知字段转换成稳定字段 code，正文不包含密码。"""

    payload = request_body()
    payload["ip_address"] = "999.1.1.1"
    payload["rtsp_port"] = 0
    payload["camera_id"] = str(uuid4_from_index(99))

    response = await client.post("/api/v1/cameras", json=payload)

    assert response.status_code == 422
    assert {item["field"]: item["code"] for item in response.json()["errors"]} == {
        "ip_address": "INVALID_IP_ADDRESS",
        "rtsp_port": "OUT_OF_RANGE",
        "camera_id": "UNKNOWN_FIELD",
    }
    assert TEST_PASSWORD not in response.text


async def test_创建接口将领域字段错误映射为问题详情(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """跨 Source 领域错误经过 Router 边界后仍保留准确数组字段路径。"""

    install_create_overrides(
        application,
        uow=FakeCameraUnitOfWork(FakeCameraStore()),
        gateway=FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT)),
    )
    payload = request_body()
    payload["sources"][1]["is_default_preview"] = True

    response = await client.post("/api/v1/cameras", json=payload)

    assert response.status_code == 422
    assert [
        (item["field"], item["code"]) for item in response.json()["errors"]
    ] == [("sources[1].is_default_preview", "MULTIPLE_DEFAULT_SOURCES")]


@pytest.mark.sensitive_data
async def test_创建接口将数据库失败映射为安全的503响应(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """数据库应用错误转换为固定 Problem，不把请求密码或底层错误写入正文。"""

    uow = FakeCameraUnitOfWork(FakeCameraStore())
    uow.commit_error = CameraPersistenceOperationError()
    install_create_overrides(
        application,
        uow=uow,
        gateway=FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT)),
    )

    response = await client.post("/api/v1/cameras", json=request_body())

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "DATABASE_UNAVAILABLE"
    assert TEST_PASSWORD not in response.text
    assert "SQL" not in response.text
