"""Camera 聚合创建、更新、重建和敏感数据回归测试。"""

import logging
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.modules.cameras.domain import (
    Camera,
    CameraAggregateCorruptedError,
    CameraSource,
    CameraSourceChange,
    CameraValidationError,
    NewCameraSource,
)
from tests.modules.cameras.builders import (
    FIXED_TIME,
    CameraBuilder,
    FixedClock,
    FixedIdGenerator,
    uuid4_from_index,
)
from tests.modules.cameras.constants import CAMERA_LEAK_SENTINEL


def error_pairs(error: CameraValidationError) -> list[tuple[str, str]]:
    return [(item.field, item.code.value) for item in error.errors]


def test_create_normalizes_sources_generates_uuid4_and_continuous_order() -> None:
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
)
def test_create_rejects_missing_or_ambiguous_default_sources(sources, expected) -> None:
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


def test_duplicate_normalized_suffixes_point_to_each_later_item_but_case_is_distinct() -> None:
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


def test_full_update_preserves_existing_identity_and_created_at_while_reordering() -> None:
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


def test_reordering_sources_never_changes_existing_ids() -> None:
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


def test_update_rejects_duplicate_and_foreign_source_ids_at_exact_paths() -> None:
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


def test_default_switch_only_changes_default_id_and_aggregate_timestamp() -> None:
    camera = CameraBuilder().build(source_count=2)
    target = camera.sources[1].source_id
    update_time = FIXED_TIME + timedelta(minutes=10)

    updated = camera.change_default_preview_source(target, clock=FixedClock(update_time))

    assert updated.default_preview_source_id == target
    assert updated.updated_at == update_time
    assert updated.sources == camera.sources
    assert updated.name == camera.name
    assert updated.credentials == camera.credentials


def test_update_rejects_reusing_id_of_a_removed_source() -> None:
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


def test_valid_persisted_rows_round_trip_without_changing_identity_or_time() -> None:
    original = CameraBuilder().build(source_count=2)
    restored_sources = tuple(
        CameraSource.reconstitute(
            source_id=source.source_id,
            camera_id=source.camera_id,
            name=source.name,
            url_suffix=source.url_suffix,
            sort_order=source.sort_order,
            created_at=source.created_at,
            updated_at=source.updated_at,
        )
        for source in original.sources
    )

    restored = Camera.reconstitute(
        camera_id=original.camera_id,
        name=original.name,
        ip_address=original.ip_address,
        rtsp_port=original.rtsp_port,
        username=original.credentials.username,
        password=original.credentials.password.reveal(),
        default_preview_source_id=original.default_preview_source_id,
        sources=restored_sources,
        created_at=original.created_at,
        updated_at=original.updated_at,
    )

    assert restored == original


def reconstituted_source(
    *,
    source_id: UUID,
    camera_id: UUID,
    sort_order: int,
    suffix: str,
) -> CameraSource:
    return CameraSource.reconstitute(
        source_id=source_id,
        camera_id=camera_id,
        name=f"Source {sort_order}",
        url_suffix=suffix,
        sort_order=sort_order,
        created_at=FIXED_TIME,
        updated_at=FIXED_TIME,
    )


@pytest.mark.parametrize("corruption", ["no_sources", "broken_order", "missing_default", "foreign"])
def test_reconstitution_rejects_corrupted_aggregate_without_silent_repair(corruption: str) -> None:
    camera_id = uuid4_from_index(1)
    source_id = uuid4_from_index(2)
    default_id = source_id
    sources: tuple[CameraSource, ...]
    if corruption == "no_sources":
        sources = ()
    elif corruption == "broken_order":
        sources = (
            reconstituted_source(
                source_id=source_id,
                camera_id=camera_id,
                sort_order=1,
                suffix="path/1",
            ),
        )
    elif corruption == "missing_default":
        sources = (
            reconstituted_source(
                source_id=source_id,
                camera_id=camera_id,
                sort_order=0,
                suffix="path/1",
            ),
        )
        default_id = uuid4_from_index(99)
    else:
        sources = (
            reconstituted_source(
                source_id=source_id,
                camera_id=uuid4_from_index(98),
                sort_order=0,
                suffix="path/1",
            ),
        )

    with pytest.raises(CameraAggregateCorruptedError) as caught:
        Camera.reconstitute(
            camera_id=camera_id,
            name="Camera",
            ip_address="192.0.2.10",
            rtsp_port=554,
            username="admin",
            password="database-secret",
            default_preview_source_id=default_id,
            sources=sources,
            created_at=FIXED_TIME,
            updated_at=FIXED_TIME,
        )

    assert caught.value.code == "CAMERA_AGGREGATE_INVALID"
    assert "database-secret" not in str(caught.value)
    assert "database-secret" not in repr(caught.value)


@pytest.mark.sensitive_data
def test_repr_exceptions_and_logs_do_not_contain_password_or_full_rtsp_url(caplog) -> None:
    sentinel = CAMERA_LEAK_SENTINEL
    builder = CameraBuilder()
    builder.password = sentinel
    camera = builder.build(source_count=1)
    full_url = camera.rtsp_url_for(camera.sources[0].source_id)

    assert full_url == (
        f"rtsp://admin:{CAMERA_LEAK_SENTINEL}@192.168.1.64:554/Streaming/Channels/001"
    )
    assert sentinel not in repr(camera)
    assert full_url not in repr(camera)

    with pytest.raises(CameraValidationError) as caught:
        camera.change_default_preview_source(
            uuid4_from_index(999),
            clock=FixedClock(FIXED_TIME),
        )
    assert sentinel not in str(caught.value)
    assert full_url not in str(caught.value)

    with caplog.at_level(logging.ERROR):
        logging.getLogger("test.camera.domain").error("领域失败：%r", camera)
    assert sentinel not in caplog.text
    assert full_url not in caplog.text


def test_source_reconstitution_rejects_noncanonical_persisted_suffix() -> None:
    with pytest.raises(CameraAggregateCorruptedError):
        CameraSource.reconstitute(
            source_id=uuid4_from_index(2),
            camera_id=uuid4_from_index(1),
            name="Source",
            url_suffix="///path/1",
            sort_order=0,
            created_at=datetime(2026, 8, 24, 8, 0, tzinfo=UTC),
            updated_at=datetime(2026, 8, 24, 8, 0, tzinfo=UTC),
        )


def test_fixture_builder_supports_required_source_cardinalities() -> None:
    for source_count in (1, 2, 10):
        camera = CameraBuilder().build(source_count=source_count)
        assert len(camera.sources) == source_count
        assert [source.sort_order for source in camera.sources] == list(range(source_count))
