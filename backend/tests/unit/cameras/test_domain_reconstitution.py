"""Camera 持久化数据重建与损坏检测规则测试。"""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.modules.cameras.domain import Camera, CameraAggregateCorruptedError, CameraSource
from tests.support.cameras.builders import FIXED_TIME, CameraBuilder, uuid4_from_index


def _reconstituted_source(
    *,
    source_id: UUID,
    camera_id: UUID,
    sort_order: int,
    suffix: str,
) -> CameraSource:
    """生成已通过单体校验的 Source，用于组合不同聚合损坏场景。"""

    return CameraSource.reconstitute(
        source_id=source_id,
        camera_id=camera_id,
        name=f"Source {sort_order}",
        url_suffix=suffix,
        sort_order=sort_order,
        created_at=FIXED_TIME,
        updated_at=FIXED_TIME,
    )


def test_合法持久化数据往返时不改变身份或时间() -> None:
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


@pytest.mark.parametrize(
    "corruption",
    ["no_sources", "broken_order", "missing_default", "foreign"],
    ids=["没有视频源", "顺序断裂", "默认源缺失", "视频源属于其他Camera"],
)
def test_重建聚合时拒绝损坏数据且不静默修复(corruption: str) -> None:
    camera_id = uuid4_from_index(1)
    source_id = uuid4_from_index(2)
    default_id = source_id
    sources: tuple[CameraSource, ...]
    if corruption == "no_sources":
        sources = ()
    elif corruption == "broken_order":
        sources = (
            _reconstituted_source(
                source_id=source_id,
                camera_id=camera_id,
                sort_order=1,
                suffix="path/1",
            ),
        )
    elif corruption == "missing_default":
        sources = (
            _reconstituted_source(
                source_id=source_id,
                camera_id=camera_id,
                sort_order=0,
                suffix="path/1",
            ),
        )
        default_id = uuid4_from_index(99)
    else:
        sources = (
            _reconstituted_source(
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


def test_重建视频源时拒绝未规范化的持久化后缀() -> None:
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
