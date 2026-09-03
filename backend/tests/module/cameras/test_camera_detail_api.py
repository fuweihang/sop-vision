"""Camera 详情 Router 的路径解析、缓存 Header 和安全错误测试。"""

import logging
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from app.core.http.middleware import TRACE_ID_HEADER
from app.core.http.trace import TraceIdLogFilter
from app.modules.cameras.api.dependencies import get_camera_clock, get_camera_unit_of_work
from app.modules.cameras.domain import (
    Camera,
    CameraAggregateCorruptedError,
    CameraDomainErrorCode,
    CameraFieldError,
)
from app.modules.stream_gateway.api.dependencies import get_stream_gateway
from app.modules.stream_gateway.ports import RuntimePath, RuntimePathSnapshot
from tests.support.cameras.builders import CameraBuilder, FixedClock, uuid4_from_index
from tests.support.cameras.constants import CAMERA_LEAK_SENTINEL
from tests.support.cameras.fakes import (
    FakeCameraStore,
    FakeCameraUnitOfWork,
    FakeStreamGateway,
)

pytestmark = pytest.mark.anyio

SNAPSHOT_AT = datetime(2026, 8, 28, 10, 0, tzinfo=UTC)
FAILED_AT = datetime(2026, 8, 28, 10, 0, 1, tzinfo=UTC)


async def store_camera(camera: Camera) -> FakeCameraStore:
    """使用 Fake 公开事务准备已提交 Camera。"""

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
) -> None:
    """覆盖详情路由的数据库、媒体和时钟依赖。"""

    application.dependency_overrides[get_camera_unit_of_work] = lambda: uow
    application.dependency_overrides[get_stream_gateway] = lambda: gateway
    application.dependency_overrides[get_camera_clock] = lambda: FixedClock(FAILED_AT)


@pytest.mark.sensitive_data
async def test_详情接口返回敏感详情并禁止缓存(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """详情响应包含凭据与完整 RTSP URL，因此必须通过 no-store 禁止缓存。"""

    builder = CameraBuilder()
    builder.username = "operator name"
    camera = builder.build(source_count=2)
    first_source = camera.sources[0]
    install_detail_overrides(
        application,
        uow=FakeCameraUnitOfWork(await store_camera(camera)),
        gateway=FakeStreamGateway(
            RuntimePathSnapshot(
                paths=(RuntimePath(name=str(first_source.source_id), available=True, online=True),),
                checked_at=SNAPSHOT_AT,
            )
        ),
    )

    response = await client.get(f"/api/v1/cameras/{camera.camera_id}")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers[TRACE_ID_HEADER]
    body = response.json()
    assert body["password"] == CAMERA_LEAK_SENTINEL
    assert body["sources"][0]["rtsp_url"] == (
        f"rtsp://operator%20name:{CAMERA_LEAK_SENTINEL}@"
        "192.168.1.64:554/Streaming/Channels/001"
    )


async def test_详情接口将未找到映射为可追踪的问题详情(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """不存在 Camera 返回 404 Problem，并只公开已经校验的路径 ID。"""

    camera_id = uuid4_from_index(999)
    install_detail_overrides(
        application,
        uow=FakeCameraUnitOfWork(FakeCameraStore()),
        gateway=FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT)),
    )

    response = await client.get(f"/api/v1/cameras/{camera_id}")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == "CAMERA_NOT_FOUND"
    assert body["context"] == {"camera_id": str(camera_id)}
    assert body["trace_id"] == response.headers[TRACE_ID_HEADER]


@pytest.mark.parametrize(
    "camera_id",
    [
        str(uuid4_from_index(0xABC)).upper(),
        "00000000-0000-4000-8000-000000000001-extra",
        "00000000-0000-1000-8000-000000000001",
    ],
)
async def test_详情接口拒绝非规范UUID4(
    client: httpx.AsyncClient,
    camera_id: str,
) -> None:
    """路径参数只接受小写、带连字符的标准 UUID v4。"""

    response = await client.get(f"/api/v1/cameras/{camera_id}")

    assert response.status_code == 422
    assert response.json()["errors"][0] == {
        "field": "camera_id",
        "code": "INVALID_UUID",
        "detail": "请输入小写、带连字符的标准 UUID v4。",
    }


@pytest.mark.sensitive_data
async def test_详情接口在问题详情和追踪日志中隐藏损坏值(
    application: FastAPI,
    client: httpx.AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """聚合损坏的 500 正文和关联日志都不能包含数据库中的敏感坏值。"""

    camera_id = uuid4_from_index(778)
    uow = FakeCameraUnitOfWork(FakeCameraStore())
    uow.cameras.get_error = CameraAggregateCorruptedError(
        CameraFieldError(
            field="password",
            code=CameraDomainErrorCode.CAMERA_AGGREGATE_INVALID,
            detail=f"损坏字段包含 {CAMERA_LEAK_SENTINEL}",
        )
    )
    install_detail_overrides(
        application,
        uow=uow,
        gateway=FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT)),
    )

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
    record = next(
        item
        for item in caplog.records
        if getattr(item, "event", None) == "camera.detail_aggregate_invalid"
    )
    assert record.trace_id == response.headers[TRACE_ID_HEADER]
    assert CAMERA_LEAK_SENTINEL not in response.text
    assert CAMERA_LEAK_SENTINEL not in caplog.text
