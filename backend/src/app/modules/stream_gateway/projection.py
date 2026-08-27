"""把完整 MediaMTX 运行态观察批量转换为框架无关 Source 投影。"""

from collections.abc import Callable, Sequence
from datetime import datetime
from uuid import UUID

from app.modules.stream_gateway.ports import (
    RuntimePathSnapshot,
    SourceRuntimeErrorCode,
    SourceRuntimeProjection,
    SourceRuntimeStatus,
    StreamGatewayInvalidResponseError,
    StreamGatewayUnavailableError,
    _validate_utc,
    _validate_uuid4,
)

RuntimeObservation = (
    RuntimePathSnapshot | StreamGatewayUnavailableError | StreamGatewayInvalidResponseError
)


def project_source_runtime(
    source_ids: Sequence[UUID],
    observation: RuntimeObservation,
    *,
    failed_at: datetime | None = None,
    whep_url_for: Callable[[UUID], str],
) -> tuple[SourceRuntimeProjection, ...]:
    """使用同一观察结果批量生成与输入顺序一致的 Source 投影。

    Args:
        source_ids: PostgreSQL 聚合给出的有序且不重复的 Source UUID v4。
        observation: 完整运行态快照，或 Adapter 已脱敏的两类失败之一。
        failed_at: Adapter 失败完成时间；成功快照禁止另传时间。
        whep_url_for: 只在 Source 严格在线时调用的公开 WHEP URL 构造函数。

    Returns:
        与 ``source_ids`` 同序的不可变投影元组。

    Raises:
        ValueError: ID 重复、ID/时间无效或成功/失败参数组合矛盾。
        TypeError: ``observation`` 不是 Port 定义的受支持类型。

    纯函数不会读取数据库、发起 Control API 请求或自行读取时钟。失败时间由调用方显式提供，
    从而让同一业务响应中的全部 Source 共享准确、可测试的完成时刻。
    """

    ordered_ids = tuple(source_ids)
    for source_id in ordered_ids:
        _validate_uuid4(source_id)
    if len(set(ordered_ids)) != len(ordered_ids):
        raise ValueError("批量状态投影不能包含重复 Source ID。")

    if isinstance(observation, RuntimePathSnapshot):
        if failed_at is not None:
            raise ValueError("成功快照禁止提供失败完成时间。")
        checked_at = observation.checked_at
        paths_by_name = {path.name: path for path in observation.paths}
        failure_code: SourceRuntimeErrorCode | None = None
    elif isinstance(observation, StreamGatewayUnavailableError):
        if failed_at is None:
            raise ValueError("Adapter 失败必须提供完成时间。")
        _validate_utc(failed_at)
        checked_at = failed_at
        paths_by_name = {}
        failure_code = SourceRuntimeErrorCode.CONTROL_API_UNAVAILABLE
    elif isinstance(observation, StreamGatewayInvalidResponseError):
        if failed_at is None:
            raise ValueError("Adapter 失败必须提供完成时间。")
        _validate_utc(failed_at)
        checked_at = failed_at
        paths_by_name = {}
        failure_code = SourceRuntimeErrorCode.CONTROL_API_INVALID_RESPONSE
    else:
        raise TypeError("运行态观察必须是完整快照或受支持的 Adapter 错误。")

    projections: list[SourceRuntimeProjection] = []
    for source_id in ordered_ids:
        if failure_code is not None:
            projections.append(_offline_projection(source_id, checked_at, failure_code))
            continue

        path = paths_by_name.get(str(source_id))
        if path is None:
            projections.append(
                _offline_projection(source_id, checked_at, SourceRuntimeErrorCode.PATH_NOT_FOUND)
            )
        elif path.available is not True:
            # available 优先于 online；两者都为 false 时必须稳定返回 NOT_AVAILABLE。
            projections.append(
                _offline_projection(
                    source_id,
                    checked_at,
                    SourceRuntimeErrorCode.PATH_NOT_AVAILABLE,
                )
            )
        elif path.online is not True:
            projections.append(
                _offline_projection(source_id, checked_at, SourceRuntimeErrorCode.PATH_OFFLINE)
            )
        else:
            projections.append(
                SourceRuntimeProjection(
                    source_id=source_id,
                    status=SourceRuntimeStatus.ONLINE,
                    last_checked_at=checked_at,
                    error=None,
                    whep_url=whep_url_for(source_id),
                )
            )

    return tuple(projections)


def _offline_projection(
    source_id: UUID,
    checked_at: datetime,
    error: SourceRuntimeErrorCode,
) -> SourceRuntimeProjection:
    """集中构造离线组合，避免各错误分支遗漏 ``whep_url=null`` 不变量。"""

    return SourceRuntimeProjection(
        source_id=source_id,
        status=SourceRuntimeStatus.OFFLINE,
        last_checked_at=checked_at,
        error=error,
        whep_url=None,
    )
