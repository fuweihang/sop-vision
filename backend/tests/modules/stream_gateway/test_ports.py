"""Stream Gateway Port 数据边界测试。"""

from uuid import UUID

import pytest

from app.modules.stream_gateway.ports import (
    DesiredSource,
    RuntimePath,
    parse_managed_path_source_id,
)

SOURCE_ID = UUID("8f14e45f-ea9d-4a7d-9b6d-8c9f0a1b2c3d")


def test_desired_source_uses_uuid_path_without_exposing_url_in_repr() -> None:
    """应用层可读取 Path 名称，但默认日志表示不能包含完整上游 URL。"""

    source_url = "rtsp://user:test-password@192.0.2.64:554/stream"
    desired = DesiredSource(source_id=SOURCE_ID, source_url=source_url)

    assert desired.path_name == str(SOURCE_ID)
    assert desired.source_on_demand is False
    assert source_url not in repr(desired)


def test_desired_source_rejects_source_on_demand() -> None:
    """非类型化调用也不能绕过持续连接规则。"""

    with pytest.raises(ValueError, match="sourceOnDemand=false"):
        DesiredSource(
            source_id=SOURCE_ID,
            source_url="rtsp://example.invalid/stream",
            source_on_demand=True,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("available,online", [(1, True), (True, "true"), (None, False)])
def test_runtime_path_requires_strict_booleans(available: object, online: object) -> None:
    """数字、字符串和缺失字段不能冒充 MediaMTX 布尔状态。"""

    with pytest.raises(TypeError, match="严格布尔值"):
        RuntimePath(name=str(SOURCE_ID), available=available, online=online)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "name",
    [
        str(SOURCE_ID).upper(),
        str(SOURCE_ID).replace("-", ""),
        "00000000-0000-1000-8000-000000000001",
        "all_others",
        "",
    ],
)
def test_managed_path_parser_rejects_noncanonical_or_non_v4_names(name: str) -> None:
    """宽松 UUID 可解析的别名也不能取得 Cameras Path 所有权。"""

    assert parse_managed_path_source_id(name) is None


def test_managed_path_parser_returns_canonical_uuid4() -> None:
    """标准小写 UUID v4 Path 与 Source ID 一一对应。"""

    assert parse_managed_path_source_id(str(SOURCE_ID)) == SOURCE_ID
