"""真实 FastAPI Router 的 Camera 创建请求、响应和错误协议测试。"""

from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from app.core.http.middleware import TRACE_ID_HEADER
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
from tests.modules.cameras.builders import FixedClock, FixedIdGenerator, uuid4_from_index
from tests.modules.cameras.fakes import (
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
    """让 Router 测试完全控制请求事务、媒体观察、ID 和时间。"""

    id_generator = FixedIdGenerator(uuid4_from_index(index) for index in range(1, 4))
    clock = FixedClock(CREATED_AT)
    application.dependency_overrides[get_camera_unit_of_work] = lambda: uow
    application.dependency_overrides[get_stream_gateway] = lambda: gateway
    application.dependency_overrides[get_camera_id_generator] = lambda: id_generator
    application.dependency_overrides[get_camera_clock] = lambda: clock


async def test_create_camera_router_returns_complete_detail_and_protocol_headers(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """成功响应包含完整展示 URL、同批投影、Location、no-store 和 Trace Header。"""

    first_source_id = uuid4_from_index(2)
    gateway = FakeStreamGateway(
        RuntimePathSnapshot(
            paths=(RuntimePath(name=str(first_source_id), available=True, online=True),),
            checked_at=SNAPSHOT_AT,
        )
    )
    store = FakeCameraStore()
    uow = FakeCameraUnitOfWork(store)
    install_create_overrides(application, uow=uow, gateway=gateway)

    response = await client.post("/api/v1/cameras", json=request_body())

    assert response.status_code == 201
    assert response.headers["location"] == f"/api/v1/cameras/{uuid4_from_index(1)}"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers[TRACE_ID_HEADER]
    body = response.json()
    assert body["camera_id"] == str(uuid4_from_index(1))
    assert body["name"] == "洗手区 01"
    assert body["username"] == "operator name"
    assert body["password"] == TEST_PASSWORD
    assert body["default_preview_source_id"] == str(first_source_id)
    assert body["status"] == "DEGRADED"
    assert body["online_source_count"] == 1
    assert body["source_count"] == 2
    assert [item["source_id"] for item in body["sources"]] == [
        str(first_source_id),
        str(uuid4_from_index(3)),
    ]
    assert body["sources"][0]["rtsp_url"] == (
        f"rtsp://operator name:{TEST_PASSWORD}@192.0.2.64:554/Streaming/Channels/101"
    )
    assert body["sources"][0]["whep_url"] == (
        f"https://media.example.invalid/{first_source_id}/whep"
    )
    assert body["sources"][1]["whep_url"] is None
    assert uow.commit_count == 1
    # 发给 MediaMTX 的上游 URL 使用组件编码，不能误用 CameraDetail 的展示 URL。
    assert gateway.ensure_calls[0].source_url.startswith(
        "rtsp://operator%20name:camera-create-api-password@192.0.2.64:554/"
    )


async def test_create_camera_router_returns_201_when_runtime_snapshot_fails(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """数据库提交后的 MediaMTX 无效响应只能令全部 Source 降级。"""

    uow = FakeCameraUnitOfWork(FakeCameraStore())
    gateway = FakeStreamGateway(StreamGatewayInvalidResponseError())
    install_create_overrides(application, uow=uow, gateway=gateway)

    response = await client.post("/api/v1/cameras", json=request_body())

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "OFFLINE"
    assert body["online_source_count"] == 0
    assert {item["error"] for item in body["sources"]} == {"MTX_CONTROL_API_INVALID_RESPONSE"}
    assert all(item["whep_url"] is None for item in body["sources"])
    assert uow.commit_count == 1
    assert gateway.runtime_snapshot_count == 1


@pytest.mark.sensitive_data
async def test_empty_sources_returns_source_required_without_echoing_request(
    client: httpx.AsyncClient,
) -> None:
    """HTTP 空数组使用创建专用 code，Problem 不回显请求密码。"""

    payload = request_body()
    payload["sources"] = []

    response = await client.post("/api/v1/cameras", json=payload)

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["errors"] == [
        {
            "field": "sources",
            "code": "SOURCE_REQUIRED",
            "detail": "创建 Camera 至少需要一路 Source。",
        }
    ]
    assert TEST_PASSWORD not in response.text


@pytest.mark.sensitive_data
async def test_create_schema_errors_keep_stable_field_codes_and_hide_input(
    client: httpx.AsyncClient,
) -> None:
    """IPv4、端口和未知字段由公共校验边界转换成稳定 code。"""

    payload = request_body()
    payload["ip_address"] = "999.1.1.1"
    payload["rtsp_port"] = 0
    payload["camera_id"] = str(uuid4_from_index(99))

    response = await client.post("/api/v1/cameras", json=payload)

    assert response.status_code == 422
    errors = {error["field"]: error["code"] for error in response.json()["errors"]}
    assert errors == {
        "ip_address": "INVALID_IP_ADDRESS",
        "rtsp_port": "OUT_OF_RANGE",
        "camera_id": "UNKNOWN_FIELD",
    }
    assert TEST_PASSWORD not in response.text


@pytest.mark.parametrize(
    ("sources", "expected_errors"),
    [
        (
            [{"name": "主码流", "url_suffix": "stream/1", "is_default_preview": False}],
            [("sources", "DEFAULT_SOURCE_REQUIRED")],
        ),
        (
            [
                {"name": "主码流", "url_suffix": "stream/1", "is_default_preview": True},
                {"name": "子码流", "url_suffix": "stream/2", "is_default_preview": True},
            ],
            [("sources[1].is_default_preview", "MULTIPLE_DEFAULT_SOURCES")],
        ),
        (
            [
                {"name": "主码流", "url_suffix": "/stream/1", "is_default_preview": True},
                {"name": "子码流", "url_suffix": "stream/1", "is_default_preview": False},
            ],
            [("sources[1].url_suffix", "DUPLICATE_SOURCE_SUFFIX")],
        ),
    ],
)
async def test_create_camera_router_preserves_domain_field_errors(
    application: FastAPI,
    client: httpx.AsyncClient,
    sources: list[dict],
    expected_errors: list[tuple[str, str]],
) -> None:
    """跨 Source 规则由 Domain 返回准确数组位置，且写库前停止。"""

    uow = FakeCameraUnitOfWork(FakeCameraStore())
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))
    install_create_overrides(application, uow=uow, gateway=gateway)
    payload = request_body()
    payload["sources"] = sources

    response = await client.post("/api/v1/cameras", json=payload)

    assert response.status_code == 422
    assert [
        (error["field"], error["code"]) for error in response.json()["errors"]
    ] == expected_errors
    assert uow.commit_count == 0
    assert gateway.ensure_calls == []


class CommitFailingUnitOfWork(FakeCameraUnitOfWork):
    """Router 测试使用的确定数据库失败。"""

    async def commit(self) -> None:
        self.commit_count += 1
        raise CameraPersistenceOperationError


@pytest.mark.sensitive_data
async def test_create_camera_database_failure_returns_safe_503_and_zero_media(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """提交失败映射为固定 503，且 Problem 不包含请求或数据库内部信息。"""

    uow = CommitFailingUnitOfWork(FakeCameraStore())
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))
    install_create_overrides(application, uow=uow, gateway=gateway)

    response = await client.post("/api/v1/cameras", json=request_body())

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "DATABASE_UNAVAILABLE"
    assert TEST_PASSWORD not in response.text
    assert "SQL" not in response.text
    assert uow.rollback_count == 1
    assert gateway.ensure_calls == []
    assert gateway.runtime_snapshot_count == 0
