"""完整更新 Camera 聚合，并在提交后按最小差异同步媒体运行态。"""

import asyncio
import logging
from dataclasses import dataclass, field
from ipaddress import IPv4Address

from app.modules.cameras.application.errors import (
    CameraAggregateInvalidError,
    CameraNotFoundError,
)
from app.modules.cameras.application.media import diff_camera_desired_sources
from app.modules.cameras.application.ports import CameraUnitOfWork
from app.modules.cameras.application.status import CameraRuntimeSummary, summarize_camera_runtime
from app.modules.cameras.domain import (
    Camera,
    CameraAggregateCorruptedError,
    CameraId,
    CameraSourceChange,
    Clock,
    IdGenerator,
    SourceId,
)
from app.modules.stream_gateway.ports import (
    SourceRuntimeProjection,
    StreamGatewayInvalidResponseError,
    StreamGatewayPort,
    StreamGatewayUnavailableError,
)
from app.modules.stream_gateway.projection import project_source_runtime

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, repr=False)
class UpdateCameraSourceCommand:
    """PUT 中一路 Source 的完整配置；无 ID 表示由服务端新增。"""

    name: str
    url_suffix: str = field(repr=False)
    is_default_preview: bool = False
    source_id: SourceId | None = None


@dataclass(frozen=True, slots=True, repr=False)
class UpdateCameraCommand:
    """框架无关的 Camera 完整更新输入。

    命令包含密码和全部 Source 后缀，因此根对象与子项都关闭默认表示。字段规则由现有
    ``Camera.update_configuration`` 统一执行，Application 不复制领域校验。
    """

    camera_id: CameraId
    name: str
    ip_address: str | IPv4Address
    rtsp_port: int
    username: str
    password: str = field(repr=False)
    sources: tuple[UpdateCameraSourceCommand, ...] = field(repr=False)


@dataclass(frozen=True, slots=True, repr=False)
class UpdateCameraResult:
    """更新用例的有类型结果；API 层负责白名单映射敏感详情。"""

    camera: Camera
    source_runtime: tuple[SourceRuntimeProjection, ...]
    runtime_summary: CameraRuntimeSummary


async def update_camera(
    command: UpdateCameraCommand,
    *,
    uow: CameraUnitOfWork,
    stream_gateway: StreamGatewayPort,
    id_generator: IdGenerator,
    clock: Clock,
) -> UpdateCameraResult:
    """锁定并完整更新 Camera，提交后执行媒体差异并返回一次运行态观察。

    数据库阶段只做聚合读取、领域更新、完整保存和提交；任何 MediaMTX I/O 都在提交成功
    后发生。数据库失败或提交结果未知时不会访问媒体，后台对账会根据最终数据库事实恢复。
    提交后的媒体故障不能反向回滚配置，只降级本次状态投影。

    Raises:
        CameraNotFoundError: Camera 在锁定读取或保存时已经不存在。
        CameraAggregateInvalidError: 持久化数据无法重建为合法聚合。
        CameraValidationError: 完整更新违反字段、Source 所有权或默认源规则。
        CameraPersistenceOperationError: 数据库读取、保存、提交或回滚失败。
    """

    # 聚合损坏只允许从 Repository 重建阶段转换。领域更新也可能用同一异常类型报告注入时钟
    # 或 ID 生成器违反服务端不变量，那些问题应沿用安全 INTERNAL_SERVER_ERROR，而不能误称
    # 数据库里已经存在损坏数据。
    previous: Camera | None = None
    aggregate_invalid = False
    try:
        previous = await uow.cameras.get(command.camera_id, for_update=True)
    except asyncio.CancelledError:
        try:
            await uow.rollback()
        except Exception:
            pass
        raise
    except CameraAggregateCorruptedError:
        # 先结束 Repository 查询开启的事务，再在 except 之外转换错误，切断包含具体损坏项
        # 的自动异常上下文。
        await uow.rollback()
        aggregate_invalid = True
    except Exception:
        # Repository 已把 SQLAlchemy 错误转换成脱敏应用错误；这里仅保证所有实现都结束事务。
        await uow.rollback()
        raise

    if aggregate_invalid:
        logger.error(
            "Camera 更新聚合数据无效",
            extra={
                "event": "camera.update_aggregate_invalid",
                "operation": "update_camera",
                "outcome": "failed",
                "camera_id": str(command.camera_id),
            },
        )
        raise CameraAggregateInvalidError(command.camera_id)

    if previous is None:
        # 锁定读取即使没有命中记录也会开启事务；404 前必须显式结束，且不得访问媒体服务。
        await uow.rollback()
        raise CameraNotFoundError(command.camera_id)

    try:
        updated = previous.update_configuration(
            name=command.name,
            ip_address=command.ip_address,
            rtsp_port=command.rtsp_port,
            username=command.username,
            password=command.password,
            sources=tuple(
                CameraSourceChange(
                    source_id=source.source_id,
                    name=source.name,
                    url_suffix=source.url_suffix,
                    is_default_preview=source.is_default_preview,
                )
                for source in command.sources
            ),
            id_generator=id_generator,
            clock=clock,
        )
        # 差异计算必须在提交前完成：它是纯函数，若未来领域对象出现不一致，应让数据库事务
        # 回滚，而不是先提交后才发现无法确定应更新哪些 Path。
        media_diff = diff_camera_desired_sources(previous, updated)
        await uow.cameras.save(updated)
        await uow.commit()
    except asyncio.CancelledError:
        # 取消保持原类型。Fake 或其他 UoW 不一定自行回滚，因此在尚未确认提交成功的阶段做
        # 一次防御性清理；清理普通失败不能把任务取消改写成业务 503。
        try:
            await uow.rollback()
        except Exception:
            pass
        raise
    except Exception:
        # 包括领域校验、Repository 保存和 commit 失败。真实 UoW 的部分失败路径已经回滚，
        # 再调用一次仍是安全的；这样 Fake 与未来实现也遵守相同事务要求。
        await uow.rollback()
        raise

    failed_media_operation_count = 0
    for desired_source in media_diff.ensure_sources:
        try:
            await stream_gateway.ensure_path(desired_source)
        except (StreamGatewayUnavailableError, StreamGatewayInvalidResponseError):
            # 单路受支持故障不阻止其余 ensure/release；Adapter 已负责脱敏 I/O 日志，后台
            # 对账会按最新数据库状态重试，不在这里记录 DesiredSource 或原始异常。
            failed_media_operation_count += 1

    for source_id in media_diff.release_source_ids:
        try:
            await stream_gateway.release_path(source_id)
        except (StreamGatewayUnavailableError, StreamGatewayInvalidResponseError):
            failed_media_operation_count += 1

    failed_at = None
    try:
        observation = await stream_gateway.fetch_runtime_path_snapshot()
    except (StreamGatewayUnavailableError, StreamGatewayInvalidResponseError) as error:
        observation = error
        failed_media_operation_count += 1
        # 一次读取失败只取一次完成时间，全部 Source 使用同一观察时刻。
        failed_at = clock.now()

    if failed_media_operation_count:
        logger.warning(
            "Camera 已更新，但媒体操作未全部成功",
            extra={
                "event": "camera.update_media_sync_degraded",
                "operation": "post_commit_media_sync",
                "outcome": "degraded",
                "camera_id": str(updated.camera_id),
                "failed_count": failed_media_operation_count,
            },
        )

    source_runtime = project_source_runtime(
        tuple(source.source_id for source in updated.sources),
        observation,
        failed_at=failed_at,
        whep_url_for=stream_gateway.whep_url_for,
    )
    runtime_summary = summarize_camera_runtime(updated, source_runtime)
    return UpdateCameraResult(
        camera=updated,
        source_runtime=source_runtime,
        runtime_summary=runtime_summary,
    )
