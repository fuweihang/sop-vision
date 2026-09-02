"""Camera 聚合到 MediaMTX Desired State 的共享纯函数测试。"""

import pytest

from app.modules.cameras.application.media import (
    build_camera_desired_sources,
    build_desired_source,
    diff_camera_desired_sources,
)
from app.modules.cameras.domain import CameraSourceChange
from tests.modules.cameras.builders import (
    FIXED_TIME,
    CameraBuilder,
    FixedClock,
    FixedIdGenerator,
    uuid4_from_index,
)


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


def test_media_diff_ignores_name_order_and_default_only_changes() -> None:
    """展示字段和默认源不改变上游连接，不应重载任何 Path。"""

    camera = CameraBuilder().build(source_count=2)
    first, second = camera.sources
    updated = camera.update_configuration(
        name="新的 Camera 名称",
        ip_address=camera.ip_address,
        rtsp_port=camera.rtsp_port,
        username=camera.credentials.username,
        password=camera.credentials.password.reveal(),
        sources=(
            CameraSourceChange(
                source_id=second.source_id,
                name="前移并改名",
                url_suffix=second.url_suffix,
                is_default_preview=True,
            ),
            CameraSourceChange(
                source_id=first.source_id,
                name="后移并改名",
                url_suffix=first.url_suffix,
                is_default_preview=False,
            ),
        ),
        id_generator=FixedIdGenerator(()),
        clock=FixedClock(FIXED_TIME),
    )

    diff = diff_camera_desired_sources(camera, updated)

    assert diff.ensure_sources == ()
    assert diff.release_source_ids == ()


def test_media_diff_ensures_changed_and_new_sources_then_releases_deleted_in_old_order() -> None:
    """后缀变化与新增按新顺序 ensure，删除项按旧顺序 release。"""

    camera = CameraBuilder().build(source_count=3)
    first, second, third = camera.sources
    new_source_id = uuid4_from_index(99)
    updated = camera.update_configuration(
        name=camera.name,
        ip_address=camera.ip_address,
        rtsp_port=camera.rtsp_port,
        username=camera.credentials.username,
        password=camera.credentials.password.reveal(),
        sources=(
            CameraSourceChange(
                source_id=second.source_id,
                name=second.name,
                url_suffix="changed/stream/2",
                is_default_preview=True,
            ),
            CameraSourceChange(
                name="新增 Source",
                url_suffix="new/stream",
                is_default_preview=False,
            ),
        ),
        id_generator=FixedIdGenerator((new_source_id,)),
        clock=FixedClock(FIXED_TIME),
    )

    diff = diff_camera_desired_sources(camera, updated)

    assert tuple(item.source_id for item in diff.ensure_sources) == (
        second.source_id,
        new_source_id,
    )
    assert diff.release_source_ids == (first.source_id, third.source_id)


def test_media_diff_ensures_every_current_source_when_connection_changes() -> None:
    """Camera 地址、端口或凭据变化会改变所有上游 URL，因此全部 Path 都需 ensure。"""

    camera = CameraBuilder().build(source_count=2)
    updated = camera.update_configuration(
        name=camera.name,
        ip_address="192.0.2.99",
        rtsp_port=8554,
        username="new-operator",
        password="new-password",
        sources=tuple(
            CameraSourceChange(
                source_id=source.source_id,
                name=source.name,
                url_suffix=source.url_suffix,
                is_default_preview=camera.is_default_preview(source.source_id),
            )
            for source in camera.sources
        ),
        id_generator=FixedIdGenerator(()),
        clock=FixedClock(FIXED_TIME),
    )

    diff = diff_camera_desired_sources(camera, updated)

    assert tuple(item.source_id for item in diff.ensure_sources) == tuple(
        source.source_id for source in updated.sources
    )
    assert diff.release_source_ids == ()
