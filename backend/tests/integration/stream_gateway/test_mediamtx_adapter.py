"""MediaMTX Adapter 的锁定协议、预算、写入和脱敏日志测试。"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from uuid import UUID

import httpx
import pytest
import respx

from app.modules.stream_gateway.ports import (
    DesiredSource,
    StreamGatewayInvalidResponseError,
    StreamGatewayUnavailableError,
)
from app.modules.stream_gateway.services.mediamtx import MediaMTXAdapter

pytestmark = pytest.mark.anyio

API_BASE_URL = "http://mediamtx.test:9997"
RUNTIME_LIST_URL = f"{API_BASE_URL}/v3/paths/list"
CONFIG_LIST_URL = f"{API_BASE_URL}/v3/config/paths/list"
SOURCE_ID = UUID("8f14e45f-ea9d-4a7d-9b6d-8c9f0a1b2c3d")
SECOND_SOURCE_ID = UUID("3f2504e0-4f89-41d3-9a0c-0305e82c3301")
LEAK_SENTINEL = "adapter-secret-password"


@pytest.fixture
async def adapter() -> AsyncIterator[MediaMTXAdapter]:
    """每个测试使用独立连接池，确保关闭和 mock 调用不会跨用例串扰。"""

    instance = MediaMTXAdapter(
        control_api_url=API_BASE_URL,
        request_timeout=5.0,
        public_webrtc_base_url="https://vision.example.invalid/media/",
    )
    try:
        yield instance
    finally:
        await instance.close()


def _page(*items: object, item_count: int | None = None, page_count: int = 1) -> dict:
    """构造显式分页 Fixture；调用方可覆盖声明计数制造协议漂移。"""

    return {
        "itemCount": len(items) if item_count is None else item_count,
        "pageCount": page_count,
        "items": list(items),
    }


@respx.mock
async def test_runtime_snapshot_reads_all_zero_based_pages_and_degrades_bad_booleans(
    adapter: MediaMTXAdapter,
) -> None:
    """分页必须完整读取，而单 Path 的非严格布尔只影响自身在线判断。"""

    first = respx.get(
        RUNTIME_LIST_URL,
        params={"page": 0, "itemsPerPage": 100},
    ).mock(
        return_value=httpx.Response(
            200,
            json=_page(
                {"name": str(SOURCE_ID), "available": True, "online": True},
                item_count=2,
                page_count=2,
            ),
        )
    )
    second = respx.get(
        RUNTIME_LIST_URL,
        params={"page": 1, "itemsPerPage": 100},
    ).mock(
        return_value=httpx.Response(
            200,
            json=_page(
                {
                    "name": str(SECOND_SOURCE_ID),
                    "available": "true",
                    "online": 1,
                },
                item_count=2,
                page_count=2,
            ),
        )
    )

    snapshot = await adapter.fetch_runtime_path_snapshot()

    assert first.called and second.called
    assert tuple(path.name for path in snapshot.paths) == (str(SOURCE_ID), str(SECOND_SOURCE_ID))
    assert snapshot.paths[0].available is True and snapshot.paths[0].online is True
    assert snapshot.paths[1].available is False and snapshot.paths[1].online is False
    assert snapshot.checked_at.utcoffset().total_seconds() == 0


@respx.mock
async def test_empty_snapshot_requires_zero_page_count(adapter: MediaMTXAdapter) -> None:
    """MediaMTX 的空集合固定表示为 itemCount=0、pageCount=0 和空 items。"""

    route = respx.get(RUNTIME_LIST_URL).mock(
        return_value=httpx.Response(
            200,
            json={"itemCount": 0, "pageCount": 0, "items": []},
        )
    )

    snapshot = await adapter.fetch_runtime_path_snapshot()

    assert route.call_count == 1
    assert snapshot.paths == ()


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"itemCount": True, "pageCount": 0, "items": []},
        {"itemCount": 0, "pageCount": 1, "items": []},
        {"itemCount": 1, "pageCount": 1, "items": []},
        _page({"name": ""}),
        _page({"name": str(SOURCE_ID)}, {"name": str(SOURCE_ID)}),
        _page({"name": str(SOURCE_ID)}, item_count=2),
    ],
)
@respx.mock
async def test_runtime_snapshot_rejects_invalid_json_pagination_or_names(
    adapter: MediaMTXAdapter,
    payload: object,
) -> None:
    """无法证明完整性的成功响应必须整份失败，不能返回部分 Path。"""

    respx.get(RUNTIME_LIST_URL).mock(return_value=httpx.Response(200, json=payload))

    with pytest.raises(StreamGatewayInvalidResponseError) as error:
        await adapter.fetch_runtime_path_snapshot()

    assert error.value.__context__ is None


@respx.mock
async def test_runtime_snapshot_rejects_counter_change_and_early_empty_page(
    adapter: MediaMTXAdapter,
) -> None:
    """第一页冻结计数；后续页即使 HTTP 成功也不能改变页数或提前为空。"""

    respx.get(RUNTIME_LIST_URL, params={"page": 0, "itemsPerPage": 100}).mock(
        return_value=httpx.Response(
            200,
            json=_page({"name": str(SOURCE_ID)}, item_count=2, page_count=2),
        )
    )
    respx.get(RUNTIME_LIST_URL, params={"page": 1, "itemsPerPage": 100}).mock(
        return_value=httpx.Response(
            200,
            json={"itemCount": 2, "pageCount": 3, "items": []},
        )
    )

    with pytest.raises(StreamGatewayInvalidResponseError):
        await adapter.fetch_runtime_path_snapshot()


@respx.mock
async def test_snapshot_classifies_invalid_json_http_and_network_failures_without_retry(
    adapter: MediaMTXAdapter,
) -> None:
    """成功响应内容错误与依赖不可用必须稳定分类，且每次调用只发送一次请求。"""

    invalid_json = respx.get(RUNTIME_LIST_URL).mock(
        return_value=httpx.Response(200, content=b"not-json")
    )
    with pytest.raises(StreamGatewayInvalidResponseError):
        await adapter.fetch_runtime_path_snapshot()
    assert invalid_json.call_count == 1

    respx.reset()
    http_failure = respx.get(RUNTIME_LIST_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(StreamGatewayUnavailableError):
        await adapter.fetch_runtime_path_snapshot()
    assert http_failure.call_count == 1

    respx.reset()
    request = httpx.Request("GET", RUNTIME_LIST_URL)
    network_failure = respx.get(RUNTIME_LIST_URL).mock(
        side_effect=httpx.ConnectError("测试网络失败", request=request)
    )
    with pytest.raises(StreamGatewayUnavailableError) as error:
        await adapter.fetch_runtime_path_snapshot()
    assert network_failure.call_count == 1
    assert error.value.__context__ is None


@respx.mock
async def test_snapshot_total_budget_cancels_in_progress_request(
    adapter: MediaMTXAdapter,
) -> None:
    """500ms 是跨整个快照的外层预算，不能退化为每页单独等待 Client timeout。"""

    cancelled = asyncio.Event()
    request_count = 0

    async def delayed_response(_request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        try:
            await asyncio.sleep(2)
        finally:
            cancelled.set()
        return httpx.Response(200, json={"itemCount": 0, "pageCount": 0, "items": []})

    respx.get(RUNTIME_LIST_URL).mock(side_effect=delayed_response)
    started_at = time.monotonic()
    with pytest.raises(StreamGatewayUnavailableError):
        await adapter.fetch_runtime_path_snapshot()

    assert time.monotonic() - started_at < 0.9
    # respx 只在 callback 正常返回后登记 route.call_count；被取消时改用入口计数证明无重试。
    assert request_count == 1
    assert cancelled.is_set()


@respx.mock
async def test_config_snapshot_preserves_unknown_managed_fields_and_isolates_unmanaged_paths(
    adapter: MediaMTXAdapter,
) -> None:
    """对账可识别受管漂移，但非 UUID Path 的无关字段不能污染 Cameras 恢复。"""

    source_url = "rtsp://encoded-user:encoded-secret@192.0.2.1:554/main"
    respx.get(CONFIG_LIST_URL, params={"page": 0, "itemsPerPage": 100}).mock(
        return_value=httpx.Response(
            200,
            json=_page(
                {
                    "name": str(SOURCE_ID),
                    "source": source_url,
                    "sourceOnDemand": False,
                },
                {
                    "name": str(SECOND_SOURCE_ID),
                    "source": None,
                    "sourceOnDemand": "false",
                },
                item_count=3,
                page_count=2,
            ),
        )
    )
    respx.get(CONFIG_LIST_URL, params={"page": 1, "itemsPerPage": 100}).mock(
        return_value=httpx.Response(
            200,
            json=_page(
                {"name": "all_others", "source": {"unexpected": "shape"}},
                item_count=3,
                page_count=2,
            ),
        )
    )

    snapshot = await adapter.fetch_config_path_snapshot()

    assert snapshot.paths[0].source_url == source_url
    assert snapshot.paths[0].source_on_demand is False
    assert snapshot.paths[1].source_url is None
    assert snapshot.paths[1].source_on_demand is None
    assert snapshot.paths[2].source_url is None
    assert snapshot.paths[2].source_on_demand is None
    assert source_url not in repr(snapshot)


@pytest.mark.sensitive_data
@respx.mock
async def test_ensure_replace_release_and_logs_are_idempotent_and_redacted(
    adapter: MediaMTXAdapter,
    caplog,
) -> None:
    """覆盖写入使用同一 UUID Path，404 删除成功，日志不包含上游秘密。"""

    replace = respx.post(f"{API_BASE_URL}/v3/config/paths/replace/{SOURCE_ID}").mock(
        side_effect=[httpx.Response(200), httpx.Response(200)]
    )
    delete = respx.delete(f"{API_BASE_URL}/v3/config/paths/delete/{SOURCE_ID}").mock(
        side_effect=[httpx.Response(200), httpx.Response(404)]
    )
    first_url = f"rtsp://user:{LEAK_SENTINEL}@192.0.2.1:554/main"
    second_url = f"rtsp://user:{LEAK_SENTINEL}@192.0.2.2:554/updated"
    with caplog.at_level(logging.DEBUG, logger="app.modules.stream_gateway.services.mediamtx"):
        await adapter.ensure_path(DesiredSource(source_id=SOURCE_ID, source_url=first_url))
        await adapter.ensure_path(DesiredSource(source_id=SOURCE_ID, source_url=second_url))
        await adapter.release_path(SOURCE_ID)
        await adapter.release_path(SOURCE_ID)

    assert replace.call_count == 2
    assert delete.call_count == 2
    assert json.loads(replace.calls[0].request.content) == {
        "source": first_url,
        "sourceOnDemand": False,
    }
    assert json.loads(replace.calls[1].request.content)["source"] == second_url
    assert LEAK_SENTINEL not in caplog.text
    adapter_records = [record for record in caplog.records if record.name.endswith("mediamtx")]
    assert len(adapter_records) == 4
    assert {record.levelno for record in adapter_records} == {logging.DEBUG}
    assert {record.message for record in adapter_records} == {"MediaMTX 调用完成"}
    assert {record.event for record in adapter_records} == {"stream_gateway.io"}
    assert {record.source_id for record in adapter_records} == {str(SOURCE_ID)}
    assert all(not hasattr(record, "path_count") for record in adapter_records)
    assert all(not hasattr(record, "trace_id") for record in adapter_records)


@pytest.mark.sensitive_data
@respx.mock
async def test_public_error_and_failure_log_do_not_retain_response_body(
    adapter: MediaMTXAdapter,
    caplog,
) -> None:
    """上游错误正文即使含凭据，也不能进入公共异常、异常链或 Adapter 日志。"""

    route = respx.post(f"{API_BASE_URL}/v3/config/paths/replace/{SOURCE_ID}").mock(
        return_value=httpx.Response(503, text=f"upstream body {LEAK_SENTINEL}")
    )
    desired = DesiredSource(
        source_id=SOURCE_ID,
        source_url=f"rtsp://user:{LEAK_SENTINEL}@192.0.2.1:554/main",
    )

    with caplog.at_level(logging.DEBUG, logger="app.modules.stream_gateway.services.mediamtx"):
        with pytest.raises(StreamGatewayUnavailableError) as error:
            await adapter.ensure_path(desired)

    rendered_error = f"{error.value!r} {error.value}"
    assert error.value.__context__ is None
    assert LEAK_SENTINEL not in rendered_error
    assert LEAK_SENTINEL not in caplog.text
    assert "rtsp://" not in caplog.text
    assert route.call_count == 1
    record = next(record for record in caplog.records if record.name.endswith("mediamtx"))
    assert record.levelno == logging.DEBUG
    assert record.message == "MediaMTX 调用失败"
    assert record.event == "stream_gateway.io"
    assert record.operation == "ensure_path"
    assert record.outcome == "unavailable"
    assert record.error_type == "StreamGatewayUnavailableError"
    assert record.source_id == str(SOURCE_ID)
    assert not hasattr(record, "path_count")
    assert not hasattr(record, "trace_id")


@respx.mock
async def test_successful_snapshot_log_keeps_meaningful_zero_path_count(
    adapter: MediaMTXAdapter,
    caplog,
) -> None:
    """成功空快照的 paths=0 有诊断价值；缺失 Source 和错误字段则直接省略。"""

    respx.get(CONFIG_LIST_URL).mock(
        return_value=httpx.Response(200, json={"itemCount": 0, "pageCount": 0, "items": []})
    )

    with caplog.at_level(logging.DEBUG, logger="app.modules.stream_gateway.services.mediamtx"):
        await adapter.fetch_config_path_snapshot()

    record = next(record for record in caplog.records if record.name.endswith("mediamtx"))
    assert record.event == "stream_gateway.io"
    assert record.operation == "fetch_config_snapshot"
    assert record.outcome == "success"
    assert record.path_count == 0
    assert not hasattr(record, "source_id")
    assert not hasattr(record, "error_type")


async def test_whep_url_preserves_reverse_proxy_prefix(adapter: MediaMTXAdapter) -> None:
    """Adapter 暴露的 URL 只依赖受校验公开地址，不调用 Control API。"""

    assert adapter.whep_url_for(SOURCE_ID) == (
        f"https://vision.example.invalid/media/{SOURCE_ID}/whep"
    )
