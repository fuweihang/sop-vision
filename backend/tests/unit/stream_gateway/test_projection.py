"""Stream Gateway 批量状态投影的纯函数与不变量测试。"""

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.modules.stream_gateway.ports import (
    RuntimePath,
    RuntimePathSnapshot,
    SourceRuntimeErrorCode,
    SourceRuntimeProjection,
    SourceRuntimeStatus,
    StreamGatewayInvalidResponseError,
    StreamGatewayUnavailableError,
)
from app.modules.stream_gateway.projection import project_source_runtime

ONLINE_ID = UUID("3f2504e0-4f89-41d3-9a0c-0305e82c3301")
UNAVAILABLE_ID = UUID("8f14e45f-ea9d-4a7d-9b6d-8c9f0a1b2c3d")
OFFLINE_ID = UUID("6f9619ff-8b86-4e4f-9f68-bb3f8f6f4f21")
MISSING_ID = UUID("a8098c1a-f86e-41da-bd1d-86d5c2a934f5")
CHECKED_AT = datetime(2026, 8, 27, 4, 0, tzinfo=UTC)


def test_projection_preserves_order_and_applies_strict_status_priority() -> None:
    """一个完整快照应批量覆盖缺失、不可用、离线和严格在线四种稳定分支。"""

    snapshot = RuntimePathSnapshot(
        paths=(
            RuntimePath(name=str(OFFLINE_ID), available=True, online=False),
            RuntimePath(name=str(ONLINE_ID), available=True, online=True),
            RuntimePath(name=str(UNAVAILABLE_ID), available=False, online=False),
        ),
        checked_at=CHECKED_AT,
    )
    whep_calls: list[UUID] = []

    def whep_url_for(source_id: UUID) -> str:
        whep_calls.append(source_id)
        return f"https://media.example.invalid/{source_id}/whep"

    projections = project_source_runtime(
        (MISSING_ID, ONLINE_ID, UNAVAILABLE_ID, OFFLINE_ID),
        snapshot,
        whep_url_for=whep_url_for,
    )

    assert tuple(item.source_id for item in projections) == (
        MISSING_ID,
        ONLINE_ID,
        UNAVAILABLE_ID,
        OFFLINE_ID,
    )
    assert tuple(item.error for item in projections) == (
        SourceRuntimeErrorCode.PATH_NOT_FOUND,
        None,
        SourceRuntimeErrorCode.PATH_NOT_AVAILABLE,
        SourceRuntimeErrorCode.PATH_OFFLINE,
    )
    assert {item.last_checked_at for item in projections} == {CHECKED_AT}
    assert projections[1].status is SourceRuntimeStatus.ONLINE
    assert projections[1].whep_url == (f"https://media.example.invalid/{ONLINE_ID}/whep")
    assert all(item.whep_url is None for index, item in enumerate(projections) if index != 1)
    # URL 构造可能在未来包含签名或部署逻辑；离线 Source 绝不能触发这类额外工作。
    assert whep_calls == [ONLINE_ID]


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (
            StreamGatewayUnavailableError(),
            SourceRuntimeErrorCode.CONTROL_API_UNAVAILABLE,
        ),
        (
            StreamGatewayInvalidResponseError(),
            SourceRuntimeErrorCode.CONTROL_API_INVALID_RESPONSE,
        ),
    ],
)
def test_adapter_failure_projects_one_shared_completion_time(
    error: Exception,
    expected_code: SourceRuntimeErrorCode,
) -> None:
    """整份快照失败时全部 Source 使用相同 Control API 原因与调用方完成时间。"""

    projections = project_source_runtime(
        (ONLINE_ID, OFFLINE_ID),
        error,  # type: ignore[arg-type]
        failed_at=CHECKED_AT,
        whep_url_for=lambda _source_id: pytest.fail("失败投影不应生成 WHEP URL"),
    )

    assert {item.last_checked_at for item in projections} == {CHECKED_AT}
    assert {item.error for item in projections} == {expected_code}
    assert {item.status for item in projections} == {SourceRuntimeStatus.OFFLINE}


def test_projection_rejects_duplicate_ids_and_conflicting_times() -> None:
    """调用方错误应立即失败，不能生成顺序或观察时间含糊的投影。"""

    snapshot = RuntimePathSnapshot(paths=(), checked_at=CHECKED_AT)
    with pytest.raises(ValueError, match="重复 Source ID"):
        project_source_runtime(
            (ONLINE_ID, ONLINE_ID),
            snapshot,
            whep_url_for=lambda source_id: str(source_id),
        )
    with pytest.raises(ValueError, match="禁止提供失败完成时间"):
        project_source_runtime(
            (ONLINE_ID,),
            snapshot,
            failed_at=CHECKED_AT,
            whep_url_for=lambda source_id: str(source_id),
        )
    with pytest.raises(ValueError, match="必须提供完成时间"):
        project_source_runtime(
            (ONLINE_ID,),
            StreamGatewayUnavailableError(),
            whep_url_for=lambda source_id: str(source_id),
        )


@pytest.mark.parametrize(
    "projection",
    [
        lambda: SourceRuntimeProjection(
            source_id=ONLINE_ID,
            status=SourceRuntimeStatus.ONLINE,
            last_checked_at=CHECKED_AT,
            error=SourceRuntimeErrorCode.PATH_OFFLINE,
            whep_url="https://media.example.invalid/path/whep",
        ),
        lambda: SourceRuntimeProjection(
            source_id=ONLINE_ID,
            status=SourceRuntimeStatus.OFFLINE,
            last_checked_at=CHECKED_AT,
            error=None,
            whep_url=None,
        ),
        lambda: SourceRuntimeProjection(
            source_id=ONLINE_ID,
            status=SourceRuntimeStatus.ONLINE,
            last_checked_at=CHECKED_AT.astimezone(timezone(timedelta(hours=8))),
            error=None,
            whep_url="https://media.example.invalid/path/whep",
        ),
        lambda: SourceRuntimeProjection(
            source_id=ONLINE_ID,
            status=SourceRuntimeStatus.ONLINE,
            last_checked_at=CHECKED_AT.astimezone(UTC) + timedelta(hours=1),
            error=None,
            whep_url=None,
        ),
    ],
)
def test_projection_data_shape_rejects_invalid_field_combinations(projection) -> None:
    """数据形状自身应阻止 Application 层绕过纯函数构造矛盾响应。"""

    with pytest.raises(ValueError):
        projection()
