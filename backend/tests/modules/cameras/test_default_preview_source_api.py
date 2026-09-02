"""真实 FastAPI Router 的默认预览源请求、响应和错误协议测试。"""

from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from app.core.http.middleware import TRACE_ID_HEADER
from app.modules.cameras.api.dependencies import get_camera_clock, get_camera_unit_of_work
from app.modules.cameras.application import CameraPersistenceOperationError
from app.modules.cameras.domain import (
    Camera,
    CameraAggregateCorruptedError,
    CameraDomainErrorCode,
    CameraFieldError,
)
from app.modules.stream_gateway.api.dependencies import get_stream_gateway
from tests.modules.cameras.builders import CameraBuilder, FixedClock, uuid4_from_index
from tests.modules.cameras.constants import CAMERA_LEAK_SENTINEL
from tests.modules.cameras.fakes import FakeCameraStore, FakeCameraUnitOfWork

pytestmark = pytest.mark.anyio

UPDATED_AT = datetime(2026, 9, 2, 11, 0, tzinfo=UTC)


async def store_camera(camera: Camera) -> FakeCameraStore:
    """通过 Fake UoW 提交 API 测试使用的初始 Camera。"""

    store = FakeCameraStore()
    writer = FakeCameraUnitOfWork(store)
    await writer.cameras.add(camera)
    await writer.commit()
    return store


def install_overrides(application: FastAPI, uow: FakeCameraUnitOfWork) -> None:
    """注入请求级数据库与时钟，并把任何媒体依赖解析都视为测试失败。"""

    application.dependency_overrides[get_camera_unit_of_work] = lambda: uow
    application.dependency_overrides[get_camera_clock] = lambda: FixedClock(UPDATED_AT)

    def forbid_stream_gateway():
        raise AssertionError("默认预览源 PATCH 不得解析或调用 Stream Gateway。")

    application.dependency_overrides[get_stream_gateway] = forbid_stream_gateway


async def test_router_returns_minimal_confirmation_without_cache_header_or_media(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """成功响应只有三个确认字段、Trace Header，且不会解析媒体依赖。"""

    camera = CameraBuilder().build(source_count=2)
    uow = FakeCameraUnitOfWork(await store_camera(camera))
    install_overrides(application, uow)

    response = await client.patch(
        f"/api/v1/cameras/{camera.camera_id}/default-preview-source",
        json={"source_id": str(camera.sources[1].source_id)},
    )

    assert response.status_code == 200
    assert response.headers[TRACE_ID_HEADER]
    assert "cache-control" not in response.headers
    assert response.json() == {
        "camera_id": str(camera.camera_id),
        "default_preview_source_id": str(camera.sources[1].source_id),
        "updated_at": "2026-09-02T11:00:00Z",
    }
    assert uow.commit_count == 1


async def test_router_returns_source_ownership_validation_error(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """跨 Camera 或不存在 Source 由领域层映射为稳定 source_id 字段错误。"""

    camera = CameraBuilder().build(source_count=2)
    uow = FakeCameraUnitOfWork(await store_camera(camera))
    install_overrides(application, uow)

    response = await client.patch(
        f"/api/v1/cameras/{camera.camera_id}/default-preview-source",
        json={"source_id": str(uuid4_from_index(999))},
    )

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {
            "field": "source_id",
            "code": "SOURCE_NOT_OWNED_BY_CAMERA",
            "detail": "Source 不存在或不属于当前 Camera。",
        }
    ]
    assert uow.rollback_count == 1
    assert uow.commit_count == 0


async def test_router_rejects_noncanonical_source_id_and_unknown_field(
    client: httpx.AsyncClient,
) -> None:
    """Schema 在进入 Application 前拒绝非标准 UUID 和 mass-assignment 字段。"""

    camera = CameraBuilder().build(source_count=2)
    response = await client.patch(
        f"/api/v1/cameras/{camera.camera_id}/default-preview-source",
        json={
            "source_id": str(uuid4_from_index(0xABCDEF)).upper(),
            "whep_url": "https://media.example.invalid/forbidden",
        },
    )

    assert response.status_code == 422
    assert {(item["field"], item["code"]) for item in response.json()["errors"]} == {
        ("source_id", "INVALID_UUID"),
        ("whep_url", "UNKNOWN_FIELD"),
    }


async def test_router_returns_404_and_503_with_stable_problem_codes(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """Camera 不存在与数据库保存失败分别保持现有 404/503 协议。"""

    camera = CameraBuilder().build(source_count=2)
    missing_uow = FakeCameraUnitOfWork(FakeCameraStore())
    install_overrides(application, missing_uow)
    response = await client.patch(
        f"/api/v1/cameras/{camera.camera_id}/default-preview-source",
        json={"source_id": str(camera.sources[1].source_id)},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "CAMERA_NOT_FOUND"
    assert response.json()["context"] == {"camera_id": str(camera.camera_id)}

    uow = FakeCameraUnitOfWork(await store_camera(camera))
    uow.cameras.save_error = CameraPersistenceOperationError()
    install_overrides(application, uow)
    response = await client.patch(
        f"/api/v1/cameras/{camera.camera_id}/default-preview-source",
        json={"source_id": str(camera.sources[1].source_id)},
    )
    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_UNAVAILABLE"
    assert uow.rollback_count == 1


@pytest.mark.sensitive_data
async def test_router_returns_safe_aggregate_invalid_500(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """损坏聚合错误不公开领域 issues、凭据、后缀或 Camera 身份 context。"""

    camera = CameraBuilder().build(source_count=2)
    uow = FakeCameraUnitOfWork(FakeCameraStore())
    uow.cameras.get_error = CameraAggregateCorruptedError(
        CameraFieldError(
            field="sources[0].url_suffix",
            code=CameraDomainErrorCode.CAMERA_AGGREGATE_INVALID,
            detail=f"不应公开 {CAMERA_LEAK_SENTINEL}",
        )
    )
    install_overrides(application, uow)

    response = await client.patch(
        f"/api/v1/cameras/{camera.camera_id}/default-preview-source",
        json={"source_id": str(camera.sources[1].source_id)},
    )

    assert response.status_code == 500
    assert response.json()["code"] == "CAMERA_AGGREGATE_INVALID"
    assert response.json()["context"] == {}
    assert CAMERA_LEAK_SENTINEL not in response.text
    assert "url_suffix" not in response.text
