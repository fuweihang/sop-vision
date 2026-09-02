"""真实 FastAPI Router 的 Camera 完整更新请求、响应和错误协议测试。"""

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
from app.modules.cameras.domain import (
    Camera,
    CameraAggregateCorruptedError,
    CameraDomainErrorCode,
    CameraFieldError,
)
from app.modules.stream_gateway.api.dependencies import get_stream_gateway
from app.modules.stream_gateway.ports import RuntimePath, RuntimePathSnapshot
from tests.modules.cameras.builders import (
    CameraBuilder,
    FixedClock,
    FixedIdGenerator,
    uuid4_from_index,
)
from tests.modules.cameras.constants import CAMERA_LEAK_SENTINEL
from tests.modules.cameras.fakes import (
    FakeCameraStore,
    FakeCameraUnitOfWork,
    FakeStreamGateway,
)

pytestmark = pytest.mark.anyio

UPDATED_AT = datetime(2026, 9, 2, 9, 0, tzinfo=UTC)
SNAPSHOT_AT = datetime(2026, 9, 2, 9, 0, 1, tzinfo=UTC)
NEW_SOURCE_ID = uuid4_from_index(950)


async def store_camera(camera: Camera) -> FakeCameraStore:
    """通过 Fake UoW 提交 API 测试使用的初始 Camera。"""

    store = FakeCameraStore()
    writer = FakeCameraUnitOfWork(store)
    await writer.cameras.add(camera)
    await writer.commit()
    return store


def request_body(camera: Camera) -> dict:
    """返回保留第二路、增加一路并删除第一路的完整 PUT body。"""

    second = camera.sources[1]
    return {
        "name": " 更新后的 Camera ",
        "ip_address": "192.0.2.65",
        "rtsp_port": 8554,
        "username": "updated operator",
        "password": CAMERA_LEAK_SENTINEL,
        "sources": [
            {
                "source_id": str(second.source_id),
                "name": " 保留 Source ",
                "url_suffix": " /changed/stream/2 ",
                "is_default_preview": True,
            },
            {
                "name": " 新增 Source ",
                "url_suffix": " /new/stream ",
                "is_default_preview": False,
            },
        ],
    }


def install_update_overrides(
    application: FastAPI,
    *,
    uow: FakeCameraUnitOfWork,
    gateway: FakeStreamGateway,
) -> None:
    """让 PUT Router 使用每例独立的事务、媒体、ID 和时间。"""

    application.dependency_overrides[get_camera_unit_of_work] = lambda: uow
    application.dependency_overrides[get_stream_gateway] = lambda: gateway
    application.dependency_overrides[get_camera_id_generator] = lambda: FixedIdGenerator(
        (NEW_SOURCE_ID,)
    )
    application.dependency_overrides[get_camera_clock] = lambda: FixedClock(UPDATED_AT)


@pytest.mark.sensitive_data
async def test_update_camera_router_returns_complete_detail_and_no_store(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """成功 PUT 返回最新完整详情、同批运行态、Trace Header 和 no-store。"""

    camera = CameraBuilder().build(source_count=2)
    second = camera.sources[1]
    store = await store_camera(camera)
    uow = FakeCameraUnitOfWork(store)
    gateway = FakeStreamGateway(
        RuntimePathSnapshot(
            paths=(
                RuntimePath(name=str(second.source_id), available=True, online=True),
                RuntimePath(name=str(NEW_SOURCE_ID), available=True, online=True),
            ),
            checked_at=SNAPSHOT_AT,
        )
    )
    install_update_overrides(application, uow=uow, gateway=gateway)

    response = await client.put(
        f"/api/v1/cameras/{camera.camera_id}",
        json=request_body(camera),
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers[TRACE_ID_HEADER]
    assert "location" not in response.headers
    body = response.json()
    assert body["camera_id"] == str(camera.camera_id)
    assert body["name"] == "更新后的 Camera"
    assert body["ip_address"] == "192.0.2.65"
    assert body["rtsp_port"] == 8554
    assert body["username"] == "updated operator"
    assert body["password"] == CAMERA_LEAK_SENTINEL
    assert body["default_preview_source_id"] == str(second.source_id)
    assert body["status"] == "ONLINE"
    assert body["online_source_count"] == 2
    assert [item["source_id"] for item in body["sources"]] == [
        str(second.source_id),
        str(NEW_SOURCE_ID),
    ]
    assert body["sources"][0]["rtsp_url"].startswith(
        f"rtsp://updated%20operator:{CAMERA_LEAK_SENTINEL}@192.0.2.65:8554/changed/stream/2"
    )
    assert uow.commit_count == 1
    assert gateway.release_calls == [camera.sources[0].source_id]
    assert gateway.runtime_snapshot_count == 1


@pytest.mark.sensitive_data
async def test_update_camera_empty_sources_returns_source_required_without_echoing_input(
    client: httpx.AsyncClient,
) -> None:
    """PUT 空数组在 HTTP Schema 阶段返回稳定 SOURCE_REQUIRED，且不回显密码。"""

    camera = CameraBuilder().build(source_count=2)
    payload = request_body(camera)
    payload["sources"] = []

    response = await client.put(f"/api/v1/cameras/{camera.camera_id}", json=payload)

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {
            "field": "sources",
            "code": "SOURCE_REQUIRED",
            "detail": "Camera 至少需要一路 Source。",
        }
    ]
    assert CAMERA_LEAK_SENTINEL not in response.text


@pytest.mark.sensitive_data
async def test_update_camera_schema_rejects_noncanonical_source_id_and_unknown_field(
    client: httpx.AsyncClient,
) -> None:
    """Source ID 与 mass-assignment 错误保持稳定字段路径，Problem 不包含请求值。"""

    camera = CameraBuilder().build(source_count=2)
    payload = request_body(camera)
    payload["camera_id"] = str(camera.camera_id)
    payload["sources"][0]["source_id"] = str(uuid4_from_index(0xABCDEF)).upper()

    response = await client.put(f"/api/v1/cameras/{camera.camera_id}", json=payload)

    assert response.status_code == 422
    errors = {item["field"]: item["code"] for item in response.json()["errors"]}
    assert errors == {
        "camera_id": "UNKNOWN_FIELD",
        "sources[0].source_id": "INVALID_UUID",
    }
    assert CAMERA_LEAK_SENTINEL not in response.text


@pytest.mark.parametrize(
    ("source_ids", "expected_errors"),
    [
        (
            lambda camera: (camera.sources[0].source_id, camera.sources[0].source_id),
            [("sources[1].source_id", "DUPLICATE_SOURCE_ID")],
        ),
        (
            lambda camera: (camera.sources[0].source_id, uuid4_from_index(999)),
            [("sources[1].source_id", "SOURCE_NOT_OWNED_BY_CAMERA")],
        ),
    ],
)
async def test_update_camera_router_preserves_source_ownership_errors(
    application: FastAPI,
    client: httpx.AsyncClient,
    source_ids,
    expected_errors: list[tuple[str, str]],
) -> None:
    """重复或外部 Source ID 由领域层返回准确的后续数组位置。"""

    camera = CameraBuilder().build(source_count=2)
    uow = FakeCameraUnitOfWork(await store_camera(camera))
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))
    install_update_overrides(application, uow=uow, gateway=gateway)
    first_id, second_id = source_ids(camera)
    payload = request_body(camera)
    payload["sources"] = [
        {
            "source_id": str(first_id),
            "name": "Source 1",
            "url_suffix": "stream/1",
            "is_default_preview": True,
        },
        {
            "source_id": str(second_id),
            "name": "Source 2",
            "url_suffix": "stream/2",
            "is_default_preview": False,
        },
    ]

    response = await client.put(f"/api/v1/cameras/{camera.camera_id}", json=payload)

    assert response.status_code == 422
    assert [(item["field"], item["code"]) for item in response.json()["errors"]] == expected_errors
    assert uow.rollback_count == 1
    assert uow.commit_count == 0
    assert gateway.ensure_calls == []
    assert gateway.release_calls == []


async def test_update_camera_router_returns_404_without_media(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """不存在 Camera 返回带已验证 ID 的 404，并先结束事务。"""

    camera = CameraBuilder().build(source_count=2)
    uow = FakeCameraUnitOfWork(FakeCameraStore())
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))
    install_update_overrides(application, uow=uow, gateway=gateway)

    response = await client.put(
        f"/api/v1/cameras/{camera.camera_id}",
        json=request_body(camera),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "CAMERA_NOT_FOUND"
    assert response.json()["context"] == {"camera_id": str(camera.camera_id)}
    assert uow.rollback_count == 1
    assert gateway.runtime_snapshot_count == 0


@pytest.mark.sensitive_data
async def test_update_camera_router_returns_safe_aggregate_invalid_500(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """损坏聚合返回独立安全 500，不公开领域 issue 或请求敏感值。"""

    camera = CameraBuilder().build(source_count=2)
    uow = FakeCameraUnitOfWork(FakeCameraStore())
    uow.cameras.get_error = CameraAggregateCorruptedError(
        CameraFieldError(
            field="sources[0].url_suffix",
            code=CameraDomainErrorCode.CAMERA_AGGREGATE_INVALID,
            detail="不应公开的损坏后缀",
        )
    )
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))
    install_update_overrides(application, uow=uow, gateway=gateway)

    response = await client.put(
        f"/api/v1/cameras/{camera.camera_id}",
        json=request_body(camera),
    )

    assert response.status_code == 500
    assert response.json()["code"] == "CAMERA_AGGREGATE_INVALID"
    assert "不应公开" not in response.text
    assert CAMERA_LEAK_SENTINEL not in response.text
    assert uow.rollback_count == 1
    assert gateway.runtime_snapshot_count == 0


@pytest.mark.sensitive_data
async def test_update_camera_router_returns_safe_503_on_save_failure(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """数据库保存失败映射为固定 503，零媒体调用且不泄露请求内容。"""

    camera = CameraBuilder().build(source_count=2)
    uow = FakeCameraUnitOfWork(await store_camera(camera))
    uow.cameras.save_error = CameraPersistenceOperationError()
    gateway = FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT))
    install_update_overrides(application, uow=uow, gateway=gateway)

    response = await client.put(
        f"/api/v1/cameras/{camera.camera_id}",
        json=request_body(camera),
    )

    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_UNAVAILABLE"
    assert CAMERA_LEAK_SENTINEL not in response.text
    assert "SQL" not in response.text
    assert uow.rollback_count == 1
    assert gateway.ensure_calls == []
    assert gateway.release_calls == []
    assert gateway.runtime_snapshot_count == 0
