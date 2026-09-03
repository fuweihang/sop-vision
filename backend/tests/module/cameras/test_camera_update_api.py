"""Camera 完整更新 Router 的请求解析、响应 Header 和字段错误测试。"""

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
from app.modules.cameras.domain import Camera
from app.modules.stream_gateway.api.dependencies import get_stream_gateway
from app.modules.stream_gateway.ports import RuntimePath, RuntimePathSnapshot
from tests.support.cameras.builders import (
    CameraBuilder,
    FixedClock,
    FixedIdGenerator,
    uuid4_from_index,
)
from tests.support.cameras.constants import CAMERA_LEAK_SENTINEL
from tests.support.cameras.fakes import (
    FakeCameraStore,
    FakeCameraUnitOfWork,
    FakeStreamGateway,
)

pytestmark = pytest.mark.anyio

UPDATED_AT = datetime(2026, 9, 2, 9, 0, tzinfo=UTC)
SNAPSHOT_AT = datetime(2026, 9, 2, 9, 0, 1, tzinfo=UTC)
NEW_SOURCE_ID = uuid4_from_index(950)


async def store_camera(camera: Camera) -> FakeCameraStore:
    """使用 Fake 公开事务准备已提交 Camera，Router 请求只负责本次更新。"""

    store = FakeCameraStore()
    writer = FakeCameraUnitOfWork(store)
    await writer.cameras.add(camera)
    await writer.commit()
    return store


def request_body(camera: Camera) -> dict:
    """返回保留第二路并新增一路的完整 PUT 请求。"""

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
    """覆盖完整更新所需端口，避免模块测试访问真实进程外服务。"""

    application.dependency_overrides[get_camera_unit_of_work] = lambda: uow
    application.dependency_overrides[get_stream_gateway] = lambda: gateway
    application.dependency_overrides[get_camera_id_generator] = lambda: FixedIdGenerator(
        (NEW_SOURCE_ID,)
    )
    application.dependency_overrides[get_camera_clock] = lambda: FixedClock(UPDATED_AT)


@pytest.mark.sensitive_data
async def test_更新接口解析完整请求并禁止缓存(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """PUT 规范化请求并返回最新详情，敏感响应必须带 no-store 且不带 Location。"""

    camera = CameraBuilder().build(source_count=2)
    second = camera.sources[1]
    gateway = FakeStreamGateway(
        RuntimePathSnapshot(
            paths=(
                RuntimePath(name=str(second.source_id), available=True, online=True),
                RuntimePath(name=str(NEW_SOURCE_ID), available=True, online=True),
            ),
            checked_at=SNAPSHOT_AT,
        )
    )
    install_update_overrides(
        application,
        uow=FakeCameraUnitOfWork(await store_camera(camera)),
        gateway=gateway,
    )

    response = await client.put(
        f"/api/v1/cameras/{camera.camera_id}",
        json=request_body(camera),
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers[TRACE_ID_HEADER]
    assert "location" not in response.headers
    body = response.json()
    assert body["name"] == "更新后的 Camera"
    assert body["sources"][0]["url_suffix"] == "changed/stream/2"
    assert body["sources"][1]["source_id"] == str(NEW_SOURCE_ID)


@pytest.mark.sensitive_data
async def test_更新接口拒绝非规范视频源ID和未知字段(
    client: httpx.AsyncClient,
) -> None:
    """PUT 的 Source ID 与 mass-assignment 错误保留嵌套字段路径且不回显密码。"""

    camera = CameraBuilder().build(source_count=2)
    payload = request_body(camera)
    payload["camera_id"] = str(camera.camera_id)
    payload["sources"][0]["source_id"] = str(uuid4_from_index(0xABCDEF)).upper()

    response = await client.put(f"/api/v1/cameras/{camera.camera_id}", json=payload)

    assert response.status_code == 422
    assert {item["field"]: item["code"] for item in response.json()["errors"]} == {
        "camera_id": "UNKNOWN_FIELD",
        "sources[0].source_id": "INVALID_UUID",
    }
    assert CAMERA_LEAK_SENTINEL not in response.text


async def test_更新接口将视频源归属错误映射为问题详情(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """不属于当前 Camera 的 Source ID 映射为更新请求中的准确字段错误。"""

    camera = CameraBuilder().build(source_count=2)
    install_update_overrides(
        application,
        uow=FakeCameraUnitOfWork(await store_camera(camera)),
        gateway=FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT)),
    )
    payload = request_body(camera)
    payload["sources"][0]["source_id"] = str(uuid4_from_index(999))

    response = await client.put(f"/api/v1/cameras/{camera.camera_id}", json=payload)

    assert response.status_code == 422
    assert [(item["field"], item["code"]) for item in response.json()["errors"]] == [
        ("sources[0].source_id", "SOURCE_NOT_OWNED_BY_CAMERA")
    ]
