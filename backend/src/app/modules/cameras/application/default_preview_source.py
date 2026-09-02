"""切换 Camera 默认预览 Source，不访问媒体运行态。"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime

from app.modules.cameras.application.errors import (
    CameraAggregateInvalidError,
    CameraNotFoundError,
)
from app.modules.cameras.application.ports import CameraUnitOfWork
from app.modules.cameras.domain import (
    CameraAggregateCorruptedError,
    CameraId,
    Clock,
    SourceId,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, repr=False)
class SetDefaultPreviewSourceCommand:
    """默认源写请求的框架无关输入。"""

    camera_id: CameraId
    source_id: SourceId


@dataclass(frozen=True, slots=True, repr=False)
class SetDefaultPreviewSourceResult:
    """只返回调用方确认写入结果所需的非敏感字段。"""

    camera_id: CameraId
    default_preview_source_id: SourceId
    updated_at: datetime


async def set_default_preview_source(
    command: SetDefaultPreviewSourceCommand,
    *,
    uow: CameraUnitOfWork,
    clock: Clock,
) -> SetDefaultPreviewSourceResult:
    """锁定 Camera 后切换默认 Source，并在同一事务中保存完整聚合。

    默认源只是一项持久化配置，不依赖 Source 当前是否在线，也不需要读取或修改 MediaMTX。
    ``get(for_update=True)`` 与 PUT 使用同一组 Camera → Source 行锁，因此两个写端点针对同一
    Camera 时会按数据库锁顺序执行，后取得锁的合法请求成为最新状态。

    Raises:
        CameraNotFoundError: Camera 不存在。
        CameraAggregateInvalidError: 持久化数据无法重建为合法聚合。
        CameraValidationError: Source 不存在或不属于目标 Camera。
        CameraPersistenceOperationError: 数据库读取、保存、提交或回滚失败。
    """

    aggregate_invalid = False
    try:
        camera = await uow.cameras.get(command.camera_id, for_update=True)
    except asyncio.CancelledError:
        # 请求在锁定读取期间取消时仍要释放已经打开的事务。清理失败不能覆盖取消信号，避免
        # 上层把一次客户端中断误判成普通数据库错误。
        try:
            await uow.rollback()
        except Exception:
            pass
        raise
    except CameraAggregateCorruptedError:
        # Repository 的领域异常可能携带具体损坏字段。先结束事务，再在异常处理块外转换成
        # 不带 issues 的应用错误，HTTP 响应和日志都不会意外保留这些内容。
        await uow.rollback()
        aggregate_invalid = True
    except Exception:
        # Repository 会把底层数据库异常转换成脱敏应用错误；这里仍负责结束所有实现的事务。
        await uow.rollback()
        raise

    if aggregate_invalid:
        logger.error(
            "Camera 默认预览源切换发现聚合数据无效",
            extra={
                "event": "camera.default_preview_source_aggregate_invalid",
                "operation": "set_default_preview_source",
                "outcome": "failed",
                "camera_id": str(command.camera_id),
            },
        )
        raise CameraAggregateInvalidError(command.camera_id)

    if camera is None:
        # 未命中记录也会开启数据库事务；返回 404 前必须释放连接上的事务和行锁状态。
        await uow.rollback()
        raise CameraNotFoundError(command.camera_id)

    try:
        updated = camera.change_default_preview_source(command.source_id, clock=clock)
        # Repository 只接受完整聚合。这里不增加局部 Source 写接口，避免绕过默认源所有权和
        # Camera 至少包含一路 Source 等既有不变量。
        await uow.cameras.save(updated)
        await uow.commit()
    except asyncio.CancelledError:
        # 与现有 PUT 保持一致：提交阶段取消原样传播，并尽力回滚尚未提交的修改。若数据库端
        # 已经完成提交，调用方仍需通过后续读取确认最终结果，不能自动重发写请求。
        try:
            await uow.rollback()
        except Exception:
            pass
        raise
    except Exception:
        # 领域校验、保存和提交失败都不能留下 Fake 或未来 UoW 实现中的未提交工作副本。
        await uow.rollback()
        raise

    return SetDefaultPreviewSourceResult(
        camera_id=updated.camera_id,
        default_preview_source_id=updated.default_preview_source_id,
        updated_at=updated.updated_at,
    )
