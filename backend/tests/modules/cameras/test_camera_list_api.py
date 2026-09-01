"""真实 FastAPI Camera 列表路由的分页、降级、错误和脱敏协议测试。"""

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
from tests.modules.cameras.builders import CameraBuilder, FixedClock
from tests.modules.cameras.constants import CAMERA_LEAK_SENTINEL
from tests.modules.cameras.fakes import (
    FakeCameraStore,
    FakeCameraUnitOfWork,
    FakeStreamGateway,
)

pytestmark = pytest.mark.anyio

SNAPSHOT_AT = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
FAILED_AT = datetime(2026, 9, 1, 9, 0, 1, tzinfo=UTC)
SENSITIVE_LIST_FIELDS = {"username", "password", "url_suffix", "rtsp_url", "sources"}


async def store_cameras(*cameras: Camera) -> FakeCameraStore:
    """通过 Fake UoW 提交聚合，保证 API 测试不绕过 Repository 边界。"""

    store = FakeCameraStore()
    writer = FakeCameraUnitOfWork(store)
    for camera in cameras:
        await writer.cameras.add(camera)
    await writer.commit()
    return store


def install_list_overrides(
    application: FastAPI,
    *,
    uow: FakeCameraUnitOfWork,
    gateway: FakeStreamGateway,
    clock: FixedClock | None = None,
) -> None:
    """让列表 Router 使用每例隔离的数据库、媒体观察和失败时间。"""

    application.dependency_overrides[get_camera_unit_of_work] = lambda: uow
    application.dependency_overrides[get_stream_gateway] = lambda: gateway
    application.dependency_overrides[get_camera_clock] = lambda: clock or FixedClock(FAILED_AT)


@pytest.mark.sensitive_data
async def test_list_cameras_returns_non_sensitive_summaries_and_one_snapshot(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """真实 Router 返回默认 Source 摘要，不泄露详情字段，并且整页只读一次快照。"""

    first_builder = CameraBuilder()
    first_builder.name = "洗手区东侧"
    first = first_builder.build(source_count=2, id_start=1000)
    second_builder = CameraBuilder()
    second_builder.name = "装配区西侧"
    second_builder.ip_address = "192.168.1.65"
    second = second_builder.build(source_count=2, id_start=1100)
    # 第一条默认 Source 在线；第二条仅非默认 Source 在线，验证 Card 不能获得备用 Source URL。
    paths = (
        RuntimePath(name=str(first.sources[0].source_id), available=True, online=True),
        RuntimePath(name=str(second.sources[1].source_id), available=True, online=True),
    )
    uow = FakeCameraUnitOfWork(await store_cameras(first, second))
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=paths, checked_at=SNAPSHOT_AT))
    install_list_overrides(application, uow=uow, gateway=gateway)

    response = await client.get("/api/v1/cameras")

    assert response.status_code == 200
    assert response.headers[TRACE_ID_HEADER]
    assert "cache-control" not in response.headers
    body = response.json()
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["total"] == 2
    assert [item["camera_id"] for item in body["items"]] == [
        str(first.camera_id),
        str(second.camera_id),
    ]
    assert body["items"][0]["status"] == "DEGRADED"
    assert body["items"][0]["online_source_count"] == 1
    assert body["items"][0]["default_preview_source"] == {
        "source_id": str(first.sources[0].source_id),
        "name": first.sources[0].name,
        "status": "ONLINE",
        "last_checked_at": SNAPSHOT_AT.isoformat().replace("+00:00", "Z"),
        "whep_url": f"https://media.example.invalid/{first.sources[0].source_id}/whep",
    }
    assert body["items"][1]["status"] == "DEGRADED"
    assert body["items"][1]["default_preview_source"]["status"] == "OFFLINE"
    assert body["items"][1]["default_preview_source"]["whep_url"] is None
    assert all(SENSITIVE_LIST_FIELDS.isdisjoint(item) for item in body["items"])
    assert CAMERA_LEAK_SENTINEL not in response.text
    assert gateway.runtime_snapshot_count == 1
    assert uow.rollback_count == 1
    assert uow.commit_count == 0


async def test_list_cameras_applies_search_pagination_and_ignores_extra_query(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """Router 规范化 q 并把固定分页参数传给列表用例，未知 sort 不改变结果。"""

    first_builder = CameraBuilder()
    first_builder.name = "Lobby Camera"
    first = first_builder.build(source_count=1, id_start=1200)
    second_builder = CameraBuilder()
    second_builder.name = "Warehouse Camera"
    second_builder.ip_address = "192.168.1.88"
    second = second_builder.build(source_count=1, id_start=1300)
    uow = FakeCameraUnitOfWork(await store_cameras(first, second))
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))
    install_list_overrides(application, uow=uow, gateway=gateway)

    response = await client.get(
        "/api/v1/cameras",
        params={"q": "  LOBBY  ", "page": 1, "page_size": 1, "sort": "name_desc"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 1
    assert [item["camera_id"] for item in body["items"]] == [str(first.camera_id)]


async def test_list_cameras_empty_page_does_not_access_gateway(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """越界页返回真实 total 和空 items，不为零 Source 请求全量媒体快照。"""

    camera = CameraBuilder().build(source_count=1, id_start=1400)
    uow = FakeCameraUnitOfWork(await store_cameras(camera))
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))
    install_list_overrides(application, uow=uow, gateway=gateway)

    response = await client.get("/api/v1/cameras", params={"page": 2, "page_size": 20})

    assert response.status_code == 200
    assert response.json() == {"items": [], "page": 2, "page_size": 20, "total": 1}
    assert gateway.runtime_snapshot_count == 0
    assert uow.rollback_count == 1


async def test_list_cameras_returns_200_offline_when_media_snapshot_fails(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """Stream Gateway 故障只让当前页默认 Source 离线，不改变配置读取成功状态。"""

    camera = CameraBuilder().build(source_count=2, id_start=1500)
    uow = FakeCameraUnitOfWork(await store_cameras(camera))
    gateway = FakeStreamGateway(StreamGatewayUnavailableError())
    clock = FixedClock(FAILED_AT)
    install_list_overrides(application, uow=uow, gateway=gateway, clock=clock)

    response = await client.get("/api/v1/cameras")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["status"] == "OFFLINE"
    assert item["online_source_count"] == 0
    assert item["default_preview_source"]["status"] == "OFFLINE"
    assert item["default_preview_source"]["last_checked_at"] == FAILED_AT.isoformat().replace(
        "+00:00", "Z"
    )
    assert item["default_preview_source"]["whep_url"] is None
    assert clock.now_count == 1
    assert gateway.runtime_snapshot_count == 1


@pytest.mark.sensitive_data
async def test_list_cameras_returns_safe_aggregate_invalid_problem_without_identity(
    application: FastAPI,
    client: httpx.AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """批量聚合损坏返回无 context 的稳定 500，响应和日志不包含领域 issue。"""

    uow = FakeCameraUnitOfWork(FakeCameraStore())
    uow.cameras.list_error = CameraAggregateCorruptedError(
        CameraFieldError(
            field="url_suffix",
            code=CameraDomainErrorCode.CAMERA_AGGREGATE_INVALID,
            detail=f"损坏字段包含 {CAMERA_LEAK_SENTINEL}",
        )
    )
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))
    install_list_overrides(application, uow=uow, gateway=gateway)

    trace_filter = TraceIdLogFilter()
    caplog.handler.addFilter(trace_filter)
    try:
        with caplog.at_level(logging.ERROR, logger="app.modules.cameras.application.listing"):
            response = await client.get("/api/v1/cameras")
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
        if getattr(record, "event", None) == "camera.list_aggregate_invalid"
    ]
    assert len(records) == 1
    assert records[0].operation == "list_cameras"
    assert records[0].outcome == "failed"
    assert not hasattr(records[0], "camera_id")
    assert records[0].trace_id == response.headers[TRACE_ID_HEADER]
    assert CAMERA_LEAK_SENTINEL not in caplog.text
    assert uow.rollback_count == 1
    assert gateway.runtime_snapshot_count == 0


@pytest.mark.parametrize("failure_stage", ["count", "list", "rollback"])
async def test_list_cameras_returns_503_for_database_failure_without_media_access(
    application: FastAPI,
    client: httpx.AsyncClient,
    failure_stage: str,
) -> None:
    """查询或结束事务失败都返回公共数据库错误，不能变成空成功列表。"""

    camera = CameraBuilder().build(source_count=1, id_start=1600)
    uow = FakeCameraUnitOfWork(await store_cameras(camera))
    if failure_stage == "count":
        uow.cameras.count_error = CameraPersistenceOperationError()
    elif failure_stage == "list":
        uow.cameras.list_error = CameraPersistenceOperationError()
    else:

        async def fail_rollback() -> None:
            raise CameraPersistenceOperationError()

        uow.rollback = fail_rollback  # type: ignore[method-assign]
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))
    install_list_overrides(application, uow=uow, gateway=gateway)

    response = await client.get("/api/v1/cameras")

    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_UNAVAILABLE"
    assert response.json()["context"] == {}
    assert gateway.runtime_snapshot_count == 0


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"page": 0}, "page"),
        ({"page_size": 101}, "page_size"),
        ({"q": "x" * 101}, "q"),
    ],
)
async def test_list_cameras_rejects_invalid_query(
    client: httpx.AsyncClient,
    params: dict[str, int | str],
    field: str,
) -> None:
    """真实列表路由沿用公共参数边界并返回准确 query 字段。"""

    response = await client.get("/api/v1/cameras", params=params)

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == field
