"""Camera 聚合创建与配置变更规则测试。"""

from dataclasses import FrozenInstanceError
from datetime import timedelta

import pytest

from app.modules.cameras.domain import (
    Camera,
    CameraAggregateCorruptedError,
    CameraSourceChange,
    CameraValidationError,
    NewCameraSource,
)
from tests.support.cameras.builders import (
    FIXED_TIME,
    CameraBuilder,
    FixedClock,
    FixedIdGenerator,
    uuid4_from_index,
)


def error_pairs(error: CameraValidationError) -> list[tuple[str, str]]:
    """提取上层会消费的字段路径和稳定错误代码。"""

    return [(item.field, item.code.value) for item in error.errors]


def test_创建聚合时规范化视频源并生成连续顺序的UUID4() -> None:
    camera = Camera.create(
        name="  洗手区 01  ",
        ip_address="192.168.1.64",
        rtsp_port=554,
        username="admin",
        password="camera-secret",
        sources=(
            NewCameraSource("  主码流  ", "///ABC/path?x=1/", True),
            NewCameraSource("子码流", "/abc/path", False),
        ),
        id_generator=FixedIdGenerator(
            (uuid4_from_index(1), uuid4_from_index(2), uuid4_from_index(3))
        ),
        clock=FixedClock(FIXED_TIME),
    )

    assert camera.camera_id == uuid4_from_index(1)
    assert camera.camera_id.version == 4
    assert camera.name == "洗手区 01"
    assert [source.source_id for source in camera.sources] == [
        uuid4_from_index(2),
        uuid4_from_index(3),
    ]
    assert [source.sort_order for source in camera.sources] == [0, 1]
    assert [source.url_suffix for source in camera.sources] == ["ABC/path?x=1/", "abc/path"]
    assert camera.default_preview_source_id == uuid4_from_index(2)
    assert camera.is_default_preview(uuid4_from_index(2))
    assert camera.created_at == camera.updated_at == FIXED_TIME


def test_Camera聚合不可变() -> None:
    """配置变更依赖返回新聚合，不能允许调用方原地篡改已有状态。"""

    camera = CameraBuilder().build(source_count=1)

    with pytest.raises(FrozenInstanceError):
        camera.camera_id = uuid4_from_index(99)  # type: ignore[misc]


@pytest.mark.parametrize(
    ("sources", "expected"),
    [
        ((), [("sources", "SOURCE_REQUIRED")]),
        (
            (NewCameraSource("Source", "path", False),),
            [("sources", "DEFAULT_SOURCE_REQUIRED")],
        ),
        (
            (
                NewCameraSource("Source 1", "path/1", True),
                NewCameraSource("Source 2", "path/2", True),
                NewCameraSource("Source 3", "path/3", True),
            ),
            [
                ("sources[1].is_default_preview", "MULTIPLE_DEFAULT_SOURCES"),
                ("sources[2].is_default_preview", "MULTIPLE_DEFAULT_SOURCES"),
            ],
        ),
    ],
    ids=["缺少视频源", "缺少默认源", "存在多个默认源"],
)
def test_创建聚合时拒绝缺失或不唯一的默认源(sources, expected) -> None:
    with pytest.raises(CameraValidationError) as caught:
        Camera.create(
            name="Camera",
            ip_address="192.0.2.10",
            rtsp_port=554,
            username="admin",
            password="secret",
            sources=sources,
            id_generator=FixedIdGenerator((uuid4_from_index(1), uuid4_from_index(2))),
            clock=FixedClock(FIXED_TIME),
        )

    assert error_pairs(caught.value) == expected


def test_规范化后重复的后缀指向后续项目且保持大小写敏感() -> None:
    with pytest.raises(CameraValidationError) as caught:
        Camera.create(
            name="Camera",
            ip_address="192.0.2.10",
            rtsp_port=554,
            username="admin",
            password="secret",
            sources=(
                NewCameraSource("Source 1", "/ABC", True),
                NewCameraSource("Source 2", " ///ABC ", False),
                NewCameraSource("Source 3", "ABC", False),
                NewCameraSource("Source 4", "abc", False),
            ),
            id_generator=FixedIdGenerator(tuple(uuid4_from_index(i) for i in range(1, 6))),
            clock=FixedClock(FIXED_TIME),
        )

    assert error_pairs(caught.value) == [
        ("sources[1].url_suffix", "DUPLICATE_SOURCE_SUFFIX"),
        ("sources[2].url_suffix", "DUPLICATE_SOURCE_SUFFIX"),
    ]


def test_完整更新在重排时保留已有身份和创建时间() -> None:
    camera = CameraBuilder().build(source_count=2)
    first, second = camera.sources
    update_time = FIXED_TIME + timedelta(minutes=5)

    updated = camera.update_configuration(
        name="洗手区东侧 01",
        ip_address="192.168.1.65",
        rtsp_port=8554,
        username="new-admin",
        password="new-secret",
        sources=(
            CameraSourceChange(
                source_id=second.source_id,
                name="保留并前移",
                url_suffix=second.url_suffix,
                is_default_preview=True,
            ),
            CameraSourceChange(
                source_id=None,
                name="新增 Source",
                url_suffix="Streaming/Channels/201",
                is_default_preview=False,
            ),
        ),
        id_generator=FixedIdGenerator((uuid4_from_index(99),)),
        clock=FixedClock(update_time),
    )

    assert updated.camera_id == camera.camera_id
    assert updated.created_at == camera.created_at
    assert updated.updated_at == update_time
    assert [source.source_id for source in updated.sources] == [
        second.source_id,
        uuid4_from_index(99),
    ]
    assert [source.sort_order for source in updated.sources] == [0, 1]
    assert updated.sources[0].created_at == second.created_at
    assert updated.sources[0].updated_at == update_time
    assert updated.default_preview_source_id == second.source_id
    assert first.source_id not in {source.source_id for source in updated.sources}


def test_仅重排视频源不会改变已有ID() -> None:
    camera = CameraBuilder().build(source_count=2)
    first, second = camera.sources
    changes = (
        CameraSourceChange(
            source_id=second.source_id,
            name=second.name,
            url_suffix=second.url_suffix,
            is_default_preview=True,
        ),
        CameraSourceChange(
            source_id=first.source_id,
            name=first.name,
            url_suffix=first.url_suffix,
            is_default_preview=False,
        ),
    )

    updated = camera.update_configuration(
        name=camera.name,
        ip_address=camera.ip_address,
        rtsp_port=camera.rtsp_port,
        username=camera.credentials.username,
        password=camera.credentials.password.reveal(),
        sources=changes,
        id_generator=FixedIdGenerator(()),
        clock=FixedClock(FIXED_TIME + timedelta(minutes=1)),
    )

    assert [source.source_id for source in updated.sources] == [second.source_id, first.source_id]
    assert [source.sort_order for source in updated.sources] == [0, 1]


def test_更新聚合时在准确字段拒绝重复和外来视频源ID() -> None:
    camera = CameraBuilder().build(source_count=2)
    owned = camera.sources[0].source_id
    foreign = uuid4_from_index(200)

    with pytest.raises(CameraValidationError) as caught:
        camera.update_configuration(
            name=camera.name,
            ip_address=camera.ip_address,
            rtsp_port=camera.rtsp_port,
            username=camera.credentials.username,
            password=camera.credentials.password.reveal(),
            sources=(
                CameraSourceChange(
                    source_id=owned,
                    name="Source 1",
                    url_suffix="path/1",
                    is_default_preview=True,
                ),
                CameraSourceChange(
                    source_id=owned,
                    name="Source 2",
                    url_suffix="path/2",
                    is_default_preview=False,
                ),
                CameraSourceChange(
                    source_id=foreign,
                    name="Source 3",
                    url_suffix="path/3",
                    is_default_preview=False,
                ),
            ),
            id_generator=FixedIdGenerator(()),
            clock=FixedClock(FIXED_TIME),
        )

    assert error_pairs(caught.value) == [
        ("sources[1].source_id", "DUPLICATE_SOURCE_ID"),
        ("sources[2].source_id", "SOURCE_NOT_OWNED_BY_CAMERA"),
    ]


def test_切换默认源只改变默认ID和聚合更新时间() -> None:
    camera = CameraBuilder().build(source_count=2)
    target = camera.sources[1].source_id
    update_time = FIXED_TIME + timedelta(minutes=10)

    updated = camera.change_default_preview_source(target, clock=FixedClock(update_time))

    assert updated.default_preview_source_id == target
    assert updated.updated_at == update_time
    assert updated.sources == camera.sources
    assert updated.name == camera.name
    assert updated.credentials == camera.credentials


def test_更新聚合时拒绝复用已删除视频源的ID() -> None:
    """新增 Source 不得通过生成器复用本次完整更新中被删除的历史 ID。"""

    camera = CameraBuilder().build(source_count=2)
    removed, retained = camera.sources

    with pytest.raises(CameraAggregateCorruptedError):
        camera.update_configuration(
            name=camera.name,
            ip_address=camera.ip_address,
            rtsp_port=camera.rtsp_port,
            username=camera.credentials.username,
            password=camera.credentials.password.reveal(),
            sources=(
                CameraSourceChange(
                    source_id=retained.source_id,
                    name=retained.name,
                    url_suffix=retained.url_suffix,
                    is_default_preview=True,
                ),
                CameraSourceChange(
                    source_id=None,
                    name="新增 Source",
                    url_suffix="new/path",
                    is_default_preview=False,
                ),
            ),
            id_generator=FixedIdGenerator((removed.source_id,)),
            clock=FixedClock(FIXED_TIME + timedelta(minutes=1)),
        )
