"""Camera 聚合到 MediaMTX Desired State 的共享纯函数测试。"""

import pytest

from app.modules.cameras.application.media import (
    build_camera_desired_sources,
    build_desired_source,
)
from tests.modules.cameras.builders import CameraBuilder


def test_build_camera_desired_sources_preserves_order_and_encodes_credentials() -> None:
    """全部调用方共享同一编码规则，且返回顺序与 Camera Source 顺序一致。"""

    builder = CameraBuilder()
    builder.username = "operator name"
    builder.password = "p@ss:/?#"
    camera = builder.build(source_count=2)

    desired = build_camera_desired_sources(camera)

    assert tuple(item.source_id for item in desired) == tuple(
        source.source_id for source in camera.sources
    )
    assert desired[0].source_url.startswith(
        "rtsp://operator%20name:p%40ss%3A%2F%3F%23@192.168.1.64:554/"
    )
    # CameraDetail 和 MediaMTX 都应拿到可使用的编码 URL；两条路径不能再次出现一边编码、一边
    # 裸拼接的差异。
    assert desired[0].source_url == camera.rtsp_url_for(camera.sources[0].source_id)
    assert desired[0].source_on_demand is False
    assert builder.password not in repr(desired)
    assert desired[0].source_url not in repr(desired[0])


def test_build_desired_source_rejects_source_from_another_camera() -> None:
    """不能把其他 Camera 的后缀与当前设备凭据拼成错误 Path。"""

    camera = CameraBuilder().build(source_count=1, id_start=1)
    other_camera = CameraBuilder().build(source_count=1, id_start=100)

    with pytest.raises(ValueError, match="当前 Camera"):
        build_desired_source(camera, other_camera.sources[0])
