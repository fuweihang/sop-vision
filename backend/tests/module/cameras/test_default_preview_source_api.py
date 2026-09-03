"""默认预览源 Router 的请求解析、响应范围和字段错误测试。"""

from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from app.core.http.middleware import TRACE_ID_HEADER
from app.modules.cameras.api.dependencies import get_camera_clock, get_camera_unit_of_work
from app.modules.cameras.domain import Camera
from tests.support.cameras.builders import CameraBuilder, FixedClock, uuid4_from_index
from tests.support.cameras.fakes import FakeCameraStore, FakeCameraUnitOfWork

pytestmark = pytest.mark.anyio

UPDATED_AT = datetime(2026, 9, 2, 11, 0, tzinfo=UTC)


async def store_camera(camera: Camera) -> FakeCameraStore:
    """使用 Fake 公开事务准备已提交 Camera。"""

    store = FakeCameraStore()
    writer = FakeCameraUnitOfWork(store)
    await writer.cameras.add(camera)
    await writer.commit()
    return store


def install_overrides(application: FastAPI, uow: FakeCameraUnitOfWork) -> None:
    """覆盖该路由实际声明的数据库和时钟依赖。"""

    application.dependency_overrides[get_camera_unit_of_work] = lambda: uow
    application.dependency_overrides[get_camera_clock] = lambda: FixedClock(UPDATED_AT)


async def test_默认预览源接口返回最小非敏感确认信息(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """PATCH 只返回三个确认字段；响应不含凭据，因此不需要 no-store。"""

    camera = CameraBuilder().build(source_count=2)
    install_overrides(application, FakeCameraUnitOfWork(await store_camera(camera)))

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


async def test_默认预览源接口拒绝非规范ID和未知字段(
    client: httpx.AsyncClient,
) -> None:
    """请求 Schema 在调用应用流程前拒绝非标准 UUID 和未知写入字段。"""

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


async def test_默认预览源接口将视频源归属错误映射为问题详情(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """跨 Camera Source 经过 HTTP 边界后仍返回稳定 source_id 字段错误。"""

    camera = CameraBuilder().build(source_count=2)
    install_overrides(application, FakeCameraUnitOfWork(await store_camera(camera)))

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
