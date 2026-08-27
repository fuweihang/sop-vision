"""Camera 聚合级运行状态计算。

Source 的在线判定由 Stream Gateway Adapter 提供；本模块只负责把同一批 Source 投影汇总成
Camera 状态。函数不执行 I/O，也不读取时钟，因此创建、详情和列表可以复用完全相同的规则。
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.modules.cameras.domain import Camera
from app.modules.stream_gateway.ports import SourceRuntimeProjection, SourceRuntimeStatus


class CameraStatus(StrEnum):
    """Camera 聚合状态；混合在线情况固定表示为 ``DEGRADED``。"""

    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    DEGRADED = "DEGRADED"


@dataclass(frozen=True, slots=True)
class CameraRuntimeSummary:
    """同一批 Source 运行投影得到的不变 Camera 统计。"""

    status: CameraStatus
    online_source_count: int
    source_count: int


def summarize_camera_runtime(
    camera: Camera,
    source_runtime: Sequence[SourceRuntimeProjection],
) -> CameraRuntimeSummary:
    """校验投影与聚合严格同序后计算 Camera 状态和计数。

    Source ID、数量或顺序不一致说明调用方混用了不同 Camera 或不同批次。继续按位置拼装会把
    一路 Source 的状态暴露到另一路 Source 上，因此在进入 API 映射前立即拒绝。
    """

    projections = tuple(source_runtime)
    configured_ids = tuple(source.source_id for source in camera.sources)
    projected_ids = tuple(projection.source_id for projection in projections)
    if projected_ids != configured_ids:
        raise ValueError("Camera Source 投影的 ID、数量或顺序与聚合不一致。")

    source_count = len(configured_ids)
    # 合法 Camera 聚合至少有一路 Source。这里仍保留防御检查，避免未来调用方绕过领域构造后
    # 把 0 路错误计算为全部在线。
    if source_count == 0:
        raise ValueError("Camera 状态统计至少需要一路 Source。")

    online_source_count = sum(
        projection.status is SourceRuntimeStatus.ONLINE for projection in projections
    )
    if online_source_count == source_count:
        status = CameraStatus.ONLINE
    elif online_source_count == 0:
        status = CameraStatus.OFFLINE
    else:
        status = CameraStatus.DEGRADED
    return CameraRuntimeSummary(
        status=status,
        online_source_count=online_source_count,
        source_count=source_count,
    )
