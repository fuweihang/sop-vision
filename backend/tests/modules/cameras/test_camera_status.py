"""Camera 聚合级运行状态的纯函数测试。"""

from datetime import UTC, datetime

import pytest

from app.modules.cameras.application import CameraStatus, summarize_camera_runtime
from app.modules.stream_gateway.ports import (
    SourceRuntimeErrorCode,
    SourceRuntimeProjection,
    SourceRuntimeStatus,
)
from tests.modules.cameras.builders import CameraBuilder, uuid4_from_index

CHECKED_AT = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)


def projection(source_id, *, online: bool) -> SourceRuntimeProjection:
    """按在线标记生成满足 Adapter 不变量的稳定 Source 投影。"""

    if online:
        return SourceRuntimeProjection(
            source_id=source_id,
            status=SourceRuntimeStatus.ONLINE,
            last_checked_at=CHECKED_AT,
            error=None,
            whep_url=f"https://media.example.invalid/{source_id}/whep",
        )
    return SourceRuntimeProjection(
        source_id=source_id,
        status=SourceRuntimeStatus.OFFLINE,
        last_checked_at=CHECKED_AT,
        error=SourceRuntimeErrorCode.PATH_NOT_FOUND,
        whep_url=None,
    )


@pytest.mark.parametrize(
    ("online_flags", "expected_status", "expected_online"),
    [
        ((True, True), CameraStatus.ONLINE, 2),
        ((False, False), CameraStatus.OFFLINE, 0),
        ((True, False), CameraStatus.DEGRADED, 1),
    ],
)
def test_summarize_camera_runtime_uses_all_source_projections(
    online_flags: tuple[bool, ...],
    expected_status: CameraStatus,
    expected_online: int,
) -> None:
    """全在线、全离线和混合投影必须得到唯一 Camera 状态和确定计数。"""

    camera = CameraBuilder().build(source_count=2)
    summary = summarize_camera_runtime(
        camera,
        tuple(
            projection(source.source_id, online=online)
            for source, online in zip(camera.sources, online_flags, strict=True)
        ),
    )

    assert summary.status is expected_status
    assert summary.online_source_count == expected_online
    assert summary.source_count == 2


@pytest.mark.parametrize("mutation", ["missing", "reordered", "foreign"])
def test_summarize_camera_runtime_rejects_projection_mismatch(mutation: str) -> None:
    """数量、顺序或 ID 错配都不能按数组位置静默拼到错误 Source。"""

    camera = CameraBuilder().build(source_count=2)
    projections = [projection(source.source_id, online=False) for source in camera.sources]
    if mutation == "missing":
        projections.pop()
    elif mutation == "reordered":
        projections.reverse()
    else:
        projections[1] = projection(uuid4_from_index(999), online=False)

    with pytest.raises(ValueError, match="ID、数量或顺序"):
        summarize_camera_runtime(camera, projections)
