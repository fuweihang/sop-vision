"""Camera Desired State 与 MediaMTX 配置快照的纯差异计算测试。"""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.modules.cameras.application.reconciliation import calculate_reconciliation_plan
from app.modules.stream_gateway.ports import ConfiguredPath, ConfiguredPathSnapshot, DesiredSource
from tests.support.cameras.builders import uuid4_from_index

CHECKED_AT = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)
SOURCE_A = uuid4_from_index(10)
SOURCE_B = uuid4_from_index(20)
SOURCE_C = uuid4_from_index(30)
SOURCE_D = uuid4_from_index(40)


def configured_snapshot(*paths: ConfiguredPath) -> ConfiguredPathSnapshot:
    """用固定 UTC 时间构造完整远端配置快照，避免计划测试依赖真实时钟。"""

    return ConfiguredPathSnapshot(paths=paths, checked_at=CHECKED_AT)


def desired(source_id: UUID, suffix: str) -> DesiredSource:
    """构造不含真实凭据的确定性期望媒体源。"""

    return DesiredSource(source_id=source_id, source_url=f"rtsp://camera.invalid/{suffix}")


def test_对账计划覆盖缺失漂移孤儿和非托管路径() -> None:
    """差异集合必须稳定排序，并且不能删除不属于 Cameras 的 Path。"""

    desired_sources = (desired(SOURCE_C, "c"), desired(SOURCE_A, "a"), desired(SOURCE_B, "b"))
    snapshot = configured_snapshot(
        ConfiguredPath(str(SOURCE_A), desired_sources[1].source_url, False),
        ConfiguredPath(str(SOURCE_B), "rtsp://camera.invalid/old", False),
        ConfiguredPath(str(SOURCE_D), "rtsp://camera.invalid/orphan", False),
        ConfiguredPath("all_others", None, None),
    )

    plan = calculate_reconciliation_plan(desired_sources, snapshot)

    assert plan.desired_count == 3
    assert plan.managed_path_count == 3
    assert tuple(item.source_id for item in plan.ensure) == (SOURCE_B, SOURCE_C)
    assert plan.release == (SOURCE_D,)


@pytest.mark.parametrize(
    "configured",
    [
        ConfiguredPath(str(SOURCE_A), None, False),
        ConfiguredPath(str(SOURCE_A), "rtsp://camera.invalid/a", None),
        ConfiguredPath(str(SOURCE_A), "rtsp://camera.invalid/a", True),
    ],
)
def test_对账计划将未知或为真的托管字段视为漂移(
    configured: ConfiguredPath,
) -> None:
    """无法证明完全相等的受管 Path 必须重写，避免保留不安全的远端配置。"""

    target = desired(SOURCE_A, "a")

    plan = calculate_reconciliation_plan((target,), configured_snapshot(configured))

    assert plan.ensure == (target,)
