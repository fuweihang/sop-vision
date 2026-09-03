"""Camera 列表 Router 的查询解析和非敏感响应测试。"""

from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from app.core.http.middleware import TRACE_ID_HEADER
from app.modules.cameras.api.dependencies import get_camera_clock, get_camera_unit_of_work
from app.modules.cameras.domain import Camera
from app.modules.stream_gateway.api.dependencies import get_stream_gateway
from app.modules.stream_gateway.ports import RuntimePath, RuntimePathSnapshot
from tests.support.cameras.builders import CameraBuilder, FixedClock
from tests.support.cameras.constants import CAMERA_LEAK_SENTINEL
from tests.support.cameras.fakes import (
    FakeCameraStore,
    FakeCameraUnitOfWork,
    FakeStreamGateway,
)

pytestmark = pytest.mark.anyio

SNAPSHOT_AT = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
FAILED_AT = datetime(2026, 9, 1, 9, 0, 1, tzinfo=UTC)
SENSITIVE_LIST_FIELDS = {"username", "password", "url_suffix", "rtsp_url", "sources"}


async def store_cameras(*cameras: Camera) -> FakeCameraStore:
    """使用 Fake 公开事务准备已提交 Camera 列表。"""

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
) -> None:
    """覆盖列表路由的数据库、媒体和时钟依赖。"""

    application.dependency_overrides[get_camera_unit_of_work] = lambda: uow
    application.dependency_overrides[get_stream_gateway] = lambda: gateway
    application.dependency_overrides[get_camera_clock] = lambda: FixedClock(FAILED_AT)


@pytest.mark.sensitive_data
async def test_列表接口只返回非敏感摘要(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """列表只公开卡片摘要；即使 Fake 聚合含凭据，也不能进入任意 item。"""

    first_builder = CameraBuilder()
    first_builder.name = "洗手区东侧"
    first = first_builder.build(source_count=2, id_start=1000)
    second_builder = CameraBuilder()
    second_builder.name = "装配区西侧"
    second_builder.ip_address = "192.168.1.65"
    second = second_builder.build(source_count=2, id_start=1100)
    paths = (
        RuntimePath(name=str(first.sources[0].source_id), available=True, online=True),
        RuntimePath(name=str(second.sources[1].source_id), available=True, online=True),
    )
    install_list_overrides(
        application,
        uow=FakeCameraUnitOfWork(await store_cameras(first, second)),
        gateway=FakeStreamGateway(RuntimePathSnapshot(paths=paths, checked_at=SNAPSHOT_AT)),
    )

    response = await client.get("/api/v1/cameras")

    assert response.status_code == 200
    assert response.headers[TRACE_ID_HEADER]
    assert "cache-control" not in response.headers
    body = response.json()
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert [item["camera_id"] for item in body["items"]] == [
        str(first.camera_id),
        str(second.camera_id),
    ]
    assert all(SENSITIVE_LIST_FIELDS.isdisjoint(item) for item in body["items"])
    assert CAMERA_LEAK_SENTINEL not in response.text


async def test_列表接口规范化查询并忽略未知排序字段(
    application: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """Router trim 搜索词并应用分页；未声明 sort 不会改变固定结果顺序。"""

    first_builder = CameraBuilder()
    first_builder.name = "Lobby Camera"
    first = first_builder.build(source_count=1, id_start=1200)
    second_builder = CameraBuilder()
    second_builder.name = "Warehouse Camera"
    second_builder.ip_address = "192.168.1.88"
    second = second_builder.build(source_count=1, id_start=1300)
    install_list_overrides(
        application,
        uow=FakeCameraUnitOfWork(await store_cameras(first, second)),
        gateway=FakeStreamGateway(RuntimePathSnapshot(paths=(), checked_at=SNAPSHOT_AT)),
    )

    response = await client.get(
        "/api/v1/cameras",
        params={"q": "  LOBBY  ", "page": 1, "page_size": 1, "sort": "name_desc"},
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["total"], body["page"], body["page_size"]) == (1, 1, 1)
    assert [item["camera_id"] for item in body["items"]] == [str(first.camera_id)]


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"page": 0}, "page"),
        ({"page_size": 101}, "page_size"),
        ({"q": "x" * 101}, "q"),
    ],
)
async def test_列表接口拒绝无效查询(
    client: httpx.AsyncClient,
    params: dict[str, int | str],
    field: str,
) -> None:
    """分页和搜索边界在 HTTP 参数解析阶段返回对应 query 字段。"""

    response = await client.get("/api/v1/cameras", params=params)

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == field
