"""分页读取 Camera 配置，并在数据库事务外批量投影媒体运行状态。"""

import logging
from dataclasses import dataclass

from app.modules.cameras.application.errors import CameraListAggregateInvalidError
from app.modules.cameras.application.ports import CameraListCriteria, CameraUnitOfWork
from app.modules.cameras.application.status import CameraRuntimeSummary, summarize_camera_runtime
from app.modules.cameras.domain import Camera, CameraAggregateCorruptedError, Clock
from app.modules.stream_gateway.ports import (
    SourceRuntimeProjection,
    StreamGatewayInvalidResponseError,
    StreamGatewayPort,
    StreamGatewayUnavailableError,
)
from app.modules.stream_gateway.projection import project_source_runtime

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, repr=False)
class CameraListItemResult:
    """一条 Camera 配置及同批运行态；API Mapper 只能从这里逐字段构造摘要。"""

    camera: Camera
    source_runtime: tuple[SourceRuntimeProjection, ...]
    runtime_summary: CameraRuntimeSummary


@dataclass(frozen=True, slots=True, repr=False)
class CameraListResult:
    """列表用例的框架无关分页结果。"""

    items: tuple[CameraListItemResult, ...]
    page: int
    page_size: int
    total: int


async def list_cameras(
    criteria: CameraListCriteria,
    page: int,
    page_size: int,
    *,
    uow: CameraUnitOfWork,
    stream_gateway: StreamGatewayPort,
    clock: Clock,
) -> CameraListResult:
    """读取一页 Camera，并使用一次 MediaMTX 快照投影全部 Source 状态。

    count 与分页读取共享请求级 UoW。两次查询完成后用 ``rollback`` 明确结束只读事务，随后才访问
    最多占用 500ms 的 Stream Gateway，避免慢外部 I/O 长时间占用 PostgreSQL 连接。空页没有需要
    投影的 Source，因此不会发起无意义的 Control API 请求。

    持久化聚合损坏会先结束事务，再转换成不携带 Camera ID 或领域 issues 的列表级错误。转换错误
    必须在 ``except`` 外抛出，防止 Python 自动异常上下文把损坏字段保留到 HTTP 或日志边界。

    Raises:
        CameraListAggregateInvalidError: 当前页至少一个持久化聚合无法安全重建。
        CameraPersistenceOperationError: 数据库查询或结束只读事务失败。
    """

    cameras: tuple[Camera, ...] = ()
    total = 0
    aggregate_invalid = False
    try:
        # count 与 list 必须复用完全相同的规范化 criteria，否则 total 和当前页会表达不同集合。
        total = await uow.cameras.count(criteria)
        cameras = await uow.cameras.list(criteria, page, page_size)
    except CameraAggregateCorruptedError:
        # Repository 已完成 SQL 读取，但 rows_to_camera 发现跨表不变量损坏。此时事务仍可能活跃，
        # 必须先结束事务；若 rollback 自身失败，应由 UoW 转换为 DATABASE_UNAVAILABLE。
        await uow.rollback()
        aggregate_invalid = True

    if aggregate_invalid:
        logger.error(
            "Camera 列表聚合数据无效",
            extra={
                "event": "camera.list_aggregate_invalid",
                "operation": "list_cameras",
                "outcome": "failed",
            },
        )
        raise CameraListAggregateInvalidError

    # 正常只读路径同样显式 rollback。Camera/Source 都是不可变领域对象，事务结束后可以安全使用。
    await uow.rollback()
    if not cameras:
        return CameraListResult(items=(), page=page, page_size=page_size, total=total)

    failed_at = None
    try:
        observation = await stream_gateway.fetch_runtime_path_snapshot()
    except (StreamGatewayUnavailableError, StreamGatewayInvalidResponseError) as error:
        observation = error
        # Adapter 错误没有 checked_at。失败完成后只读一次时钟，让整页所有 Source 共享同一批次时间。
        failed_at = clock.now()

    # Source 主键全局唯一，按 Camera 与配置顺序展平后可以一次完成纯投影，再切回每个聚合。
    source_ids = tuple(source.source_id for camera in cameras for source in camera.sources)
    projections = project_source_runtime(
        source_ids,
        observation,
        failed_at=failed_at,
        whep_url_for=stream_gateway.whep_url_for,
    )

    items: list[CameraListItemResult] = []
    projection_offset = 0
    for camera in cameras:
        next_offset = projection_offset + len(camera.sources)
        camera_runtime = projections[projection_offset:next_offset]
        # summarize_camera_runtime 会再次核对 Source ID 与顺序，防止切片边界错误把状态串到
        # 其他 Camera。
        runtime_summary = summarize_camera_runtime(camera, camera_runtime)
        items.append(
            CameraListItemResult(
                camera=camera,
                source_runtime=camera_runtime,
                runtime_summary=runtime_summary,
            )
        )
        projection_offset = next_offset

    return CameraListResult(
        items=tuple(items),
        page=page,
        page_size=page_size,
        total=total,
    )
