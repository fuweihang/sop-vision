"""读取 Camera 完整配置，并在数据库事务外投影当前媒体状态。"""

import logging
from dataclasses import dataclass

from app.modules.cameras.application.errors import (
    CameraAggregateInvalidError,
    CameraNotFoundError,
)
from app.modules.cameras.application.ports import CameraUnitOfWork
from app.modules.cameras.application.status import CameraRuntimeSummary, summarize_camera_runtime
from app.modules.cameras.domain import Camera, CameraAggregateCorruptedError, CameraId, Clock
from app.modules.stream_gateway.ports import (
    SourceRuntimeProjection,
    StreamGatewayInvalidResponseError,
    StreamGatewayPort,
    StreamGatewayUnavailableError,
)
from app.modules.stream_gateway.projection import project_source_runtime

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, repr=False)
class CameraDetailResult:
    """详情用例的有类型结果；敏感配置只在 API Mapper 中进入 ``CameraDetail``。"""

    camera: Camera
    source_runtime: tuple[SourceRuntimeProjection, ...]
    runtime_summary: CameraRuntimeSummary


async def get_camera_detail(
    camera_id: CameraId,
    *,
    uow: CameraUnitOfWork,
    stream_gateway: StreamGatewayPort,
    clock: Clock,
) -> CameraDetailResult:
    """读取一个 Camera，并使用一次 MediaMTX 快照生成同批运行状态。

    Repository 读取会开启 PostgreSQL 只读事务。无论找到 Camera 还是确认不存在，都先通过
    ``rollback`` 结束事务，再访问最多占用 500ms 的 MediaMTX 快照，避免请求在等待网络时继续
    占用数据库事务和连接。媒体故障按既有契约降级为 200 详情；任务取消和未知错误继续传播。

    Raises:
        CameraNotFoundError: 请求 Camera 不存在。
        CameraAggregateInvalidError: 持久化数据无法重建为合法聚合。
        CameraPersistenceOperationError: 数据库读取或结束事务失败。
    """

    # 先给读取结果一个明确的可空类型。聚合损坏分支会在后面抛出独立错误，但静态分析器不会
    # 根据 ``aggregate_invalid`` 反向推断 try 内一定完成了赋值；显式初始化可避免未绑定变量，
    # 同时保留“离开 except 后再抛错”以切断包含领域 issues 的异常上下文。
    camera: Camera | None = None
    aggregate_invalid = False
    try:
        camera = await uow.cameras.get(camera_id, for_update=False)
    except CameraAggregateCorruptedError:
        # 先结束 Repository 查询开启的事务。错误转换放在 except 之外，新的应用错误就不会通过
        # 自动异常上下文保留包含具体领域 issues 的原异常。
        await uow.rollback()
        aggregate_invalid = True

    if aggregate_invalid:
        logger.error(
            "Camera 详情聚合数据无效",
            extra={
                "event": "camera.detail_aggregate_invalid",
                "operation": "get_camera",
                "outcome": "failed",
                "camera_id": str(camera_id),
            },
        )
        raise CameraAggregateInvalidError(camera_id)

    # rollback 在正常只读路径只负责明确结束事务，不会丢失已重建的不可变 Camera 对象。
    await uow.rollback()
    if camera is None:
        # 不存在时不能访问 MediaMTX；否则一个无效 ID 会产生没有业务价值的全量 Path 请求。
        raise CameraNotFoundError(camera_id)

    failed_at = None
    try:
        observation = await stream_gateway.fetch_runtime_path_snapshot()
    except (StreamGatewayUnavailableError, StreamGatewayInvalidResponseError) as error:
        observation = error
        # Adapter 失败没有快照时间，由请求 Clock 在失败完成后读取一次，全部 Source 共用该时刻。
        failed_at = clock.now()

    source_runtime = project_source_runtime(
        tuple(source.source_id for source in camera.sources),
        observation,
        failed_at=failed_at,
        whep_url_for=stream_gateway.whep_url_for,
    )
    runtime_summary = summarize_camera_runtime(camera, source_runtime)
    return CameraDetailResult(
        camera=camera,
        source_runtime=source_runtime,
        runtime_summary=runtime_summary,
    )
