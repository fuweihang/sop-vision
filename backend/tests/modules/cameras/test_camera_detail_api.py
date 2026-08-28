"""真实 FastAPI Camera 详情路由的成功、降级和错误协议测试。"""

import logging
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from app.core.http.middleware import TRACE_ID_HEADER
from app.core.http.trace import TraceIdLogFilter
from app.modules.cameras.api.dependencies import get_camera_clock, get_camera_unit_of_work
from app.modules.cameras.application import CameraPersistenceOperationError
from app.modules.cameras.domain import (
    Camera,
    CameraAggregateCorruptedError,
    CameraDomainErrorCode,
    CameraFieldError,
)
from app.modules.stream_gateway.api.dependencies import get_stream_gateway
from app.modules.stream_gateway.ports import (
    RuntimePath,
    RuntimePathSnapshot,
    StreamGatewayUnavailableError,
)
from tests.modules.cameras.builders import CameraBuilder, FixedClock, uuid4_from_index
from tests.modules.cameras.constants import CAMERA_LEAK_SENTINEL
from tests.modules.cameras.fakes import (
    FakeCameraStore,
    FakeCameraUnitOfWork,
    FakeStreamGateway,
)

pytestmark = pytest.mark.anyio

SNAPSHOT_AT = datetime(2026, 8, 28, 10, 0, tzinfo=UTC)
FAILED_AT = datetime(2026, 8, 28, 10, 0, 1, tzinfo=UTC)


async def store_camera(camera: Camera) -> FakeCameraStore:
    """通过 Fake UoW 正常提交聚合，避免 API 测试绕过 Repository 状态。"""

    store = FakeCameraStore()
    writer = FakeCameraUnitOfWork(store)
    await writer.cameras.add(camera)
    await writer.commit()
    return store


def install_detail_overrides(
    application: FastAPI,
    *,
    uow: FakeCameraUnitOfWork,
    gateway: FakeStreamGateway,
    clock: FixedClock | None = None,
) -> None:
    """让详情 Router 使用每例独立的事务、媒体快照和失败时间。"""

    application.dependency_overrides[get_camera_unit_of_work] = lambda: uow
    application.dependency_overrides[get_stream_gateway] = lambda: gateway
    application.dependency_overrides[get_camera_clock] = lambda: clock or FixedClock(FAILED_AT)


@pytest.mark.sensitive_data
async def test_get_camera_returns_complete_detail_no_store_and_one_snapshot(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """成功详情包含完整配置和同批状态，并明确禁止缓存敏感响应。"""

    camera = CameraBuilder().build(source_count=2)
    first_source = camera.sources[0]
    gateway = FakeStreamGateway(
        RuntimePathSnapshot(
            paths=(RuntimePath(name=str(first_source.source_id), available=True, online=True),),
            checked_at=SNAPSHOT_AT,
        )
    )
    uow = FakeCameraUnitOfWork(await store_camera(camera))
    install_detail_overrides(application, uow=uow, gateway=gateway)

    response = await client.get(f"/api/v1/cameras/{camera.camera_id}")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers[TRACE_ID_HEADER]
    body = response.json()
    assert body["camera_id"] == str(camera.camera_id)
    assert body["name"] == camera.name
    assert body["username"] == camera.credentials.username
    assert body["password"] == CAMERA_LEAK_SENTINEL
    assert body["default_preview_source_id"] == str(first_source.source_id)
    assert body["status"] == "DEGRADED"
    assert body["online_source_count"] == 1
    assert body["source_count"] == 2
    assert [item["source_id"] for item in body["sources"]] == [
        str(source.source_id) for source in camera.sources
    ]
    assert body["sources"][0]["rtsp_url"] == camera.rtsp_url_for(first_source.source_id)
    assert body["sources"][0]["whep_url"] == (
        f"https://media.example.invalid/{first_source.source_id}/whep"
    )
    assert body["sources"][1]["whep_url"] is None
    assert uow.rollback_count == 1
    assert uow.commit_count == 0
    assert gateway.runtime_snapshot_count == 1
    assert gateway.ensure_calls == []


async def test_get_camera_returns_200_degraded_when_media_snapshot_fails(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """MediaMTX 不可用只影响运行状态，不把可读取的数据库配置改成 503。"""

    camera = CameraBuilder().build(source_count=2)
    gateway = FakeStreamGateway(StreamGatewayUnavailableError())
    clock = FixedClock(FAILED_AT)
    uow = FakeCameraUnitOfWork(await store_camera(camera))
    install_detail_overrides(application, uow=uow, gateway=gateway, clock=clock)

    response = await client.get(f"/api/v1/cameras/{camera.camera_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "OFFLINE"
    assert body["online_source_count"] == 0
    assert {item["error"] for item in body["sources"]} == {"MTX_CONTROL_API_UNAVAILABLE"}
    assert all(item["whep_url"] is None for item in body["sources"])
    assert clock.now_count == 1
    assert gateway.runtime_snapshot_count == 1


async def test_get_camera_returns_404_with_validated_camera_context(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """不存在响应只公开已经校验的 Camera ID，并且不会访问媒体服务。"""

    camera_id = uuid4_from_index(999)
    uow = FakeCameraUnitOfWork(FakeCameraStore())
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))
    install_detail_overrides(application, uow=uow, gateway=gateway)

    response = await client.get(f"/api/v1/cameras/{camera_id}")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == "CAMERA_NOT_FOUND"
    assert body["context"] == {"camera_id": str(camera_id)}
    assert body["trace_id"] == response.headers[TRACE_ID_HEADER]
    assert uow.rollback_count == 1
    assert gateway.runtime_snapshot_count == 0


@pytest.mark.parametrize(
    "camera_id",
    [
        str(uuid4_from_index(0xABC)).upper(),
        "00000000-0000-4000-8000-000000000001-extra",
        "00000000-0000-1000-8000-000000000001",
    ],
)
async def test_get_camera_rejects_non_canonical_uuid4(
    client: httpx.AsyncClient,
    camera_id: str,
) -> None:
    """路径参数只接受小写、带连字符的标准 UUID v4。"""

    response = await client.get(f"/api/v1/cameras/{camera_id}")

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["errors"][0]["field"] == "camera_id"
    assert body["errors"][0]["code"] == "INVALID_UUID"


@pytest.mark.sensitive_data
async def test_get_camera_returns_safe_aggregate_invalid_problem_and_one_business_log(
    application: FastAPI,
    client: httpx.AsyncClient,
    caplog,
) -> None:
    """损坏聚合返回独立稳定 500，响应和业务日志都不包含领域 issue 或凭据。"""

    camera_id = uuid4_from_index(778)
    uow = FakeCameraUnitOfWork(FakeCameraStore())
    uow.cameras.get_error = CameraAggregateCorruptedError(
        CameraFieldError(
            field="password",
            code=CameraDomainErrorCode.CAMERA_AGGREGATE_INVALID,
            detail=f"损坏字段包含 {CAMERA_LEAK_SENTINEL}",
        )
    )
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))
    install_detail_overrides(application, uow=uow, gateway=gateway)

    trace_filter = TraceIdLogFilter()
    caplog.handler.addFilter(trace_filter)
    try:
        with caplog.at_level(logging.ERROR, logger="app.modules.cameras.application.detail"):
            response = await client.get(f"/api/v1/cameras/{camera_id}")
    finally:
        caplog.handler.removeFilter(trace_filter)

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == "CAMERA_AGGREGATE_INVALID"
    assert body["context"] == {}
    assert body["trace_id"] == response.headers[TRACE_ID_HEADER]
    assert CAMERA_LEAK_SENTINEL not in response.text
    records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "camera.detail_aggregate_invalid"
    ]
    assert len(records) == 1
    assert records[0].levelno == logging.ERROR
    assert records[0].operation == "get_camera"
    assert records[0].outcome == "failed"
    assert records[0].camera_id == str(camera_id)
    assert records[0].trace_id == response.headers[TRACE_ID_HEADER]
    assert CAMERA_LEAK_SENTINEL not in caplog.text
    assert uow.rollback_count == 1
    assert gateway.runtime_snapshot_count == 0


async def test_get_camera_returns_503_for_database_failure_without_media_access(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """数据库读取失败沿用公共 503，不能被错误降级成空 Camera 详情。"""

    camera_id = uuid4_from_index(779)
    uow = FakeCameraUnitOfWork(FakeCameraStore())
    uow.cameras.get_error = CameraPersistenceOperationError()
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))
    install_detail_overrides(application, uow=uow, gateway=gateway)

    response = await client.get(f"/api/v1/cameras/{camera_id}")

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "DATABASE_UNAVAILABLE"
    assert body["context"] == {}
    assert gateway.runtime_snapshot_count == 0
