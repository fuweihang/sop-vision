"""Camera Desired State 与 MediaMTX 配置的单轮对账及周期 Runner。"""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.core.http import get_trace_id
from app.modules.cameras.application.media import build_camera_desired_sources
from app.modules.cameras.application.ports import MediaReconciliationLease
from app.modules.stream_gateway.ports import (
    ConfiguredPathSnapshot,
    DesiredSource,
    StreamGatewayInvalidResponseError,
    StreamGatewayPort,
    StreamGatewayUnavailableError,
    parse_managed_path_source_id,
)

logger = logging.getLogger(__name__)

Sleep = Callable[[float], Awaitable[None]]
Jitter = Callable[[float, float], float]
MonotonicClock = Callable[[], float]


class ReconciliationOutcome(StrEnum):
    """一轮对账的稳定结果分类；日志和 Runner 退避只依赖这些值。"""

    SUCCESS = "success"
    PARTIAL_FAILURE = "partial_failure"
    SKIPPED_LOCK = "skipped_lock"
    DATABASE_ERROR = "database_error"
    GATEWAY_UNAVAILABLE = "gateway_unavailable"
    GATEWAY_INVALID_RESPONSE = "gateway_invalid_response"
    UNEXPECTED_ERROR = "unexpected_error"


@dataclass(frozen=True, slots=True)
class ReconciliationPlan:
    """纯差异计算结果；写入顺序已经固定，执行层无需再次排序。"""

    desired_count: int
    managed_path_count: int
    ensure: tuple[DesiredSource, ...]
    release: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """不含 URL、凭据或远端配置的一轮汇总。"""

    outcome: ReconciliationOutcome
    desired_count: int = 0
    managed_path_count: int = 0
    ensured_count: int = 0
    released_count: int = 0
    failed_count: int = 0

    @property
    def is_failure(self) -> bool:
        """锁竞争是正常调度结果，只有其余非成功分类会增加退避。"""

        return self.outcome not in {
            ReconciliationOutcome.SUCCESS,
            ReconciliationOutcome.SKIPPED_LOCK,
        }


def calculate_reconciliation_plan(
    desired_sources: Sequence[DesiredSource],
    remote_snapshot: ConfiguredPathSnapshot,
) -> ReconciliationPlan:
    """计算缺失/漂移的 ensure 与受管孤儿 release，不执行任何 I/O。

    远端 ``source`` 或 ``sourceOnDemand`` 未知时不能假定配置正确，必须用完整 Desired State
    覆盖。非标准 UUID v4 Path 不属于 Cameras，即使名称看起来相近也不会被删除。
    """

    desired_tuple = tuple(desired_sources)
    # Source ID 同时是 MediaMTX Path 名称和双方状态的关联键。若数据库意外产生重复 ID，继续
    # 构造 dict 会静默覆盖其中一路，因此必须在任何远端写入之前拒绝整份期望状态。
    desired_by_id = {source.source_id: source for source in desired_tuple}
    if len(desired_by_id) != len(desired_tuple):
        raise ValueError("媒体期望状态不能包含重复 Source ID。")

    managed_paths = {}
    for path in remote_snapshot.paths:
        # MediaMTX 允许任意名称。只有严格的标准 UUID v4 才属于 Cameras，其他 Path 即使配置
        # 看起来像 RTSP Source 也不能进入差异集合，否则可能误删其他业务维护的配置。
        source_id = parse_managed_path_source_id(path.name)
        if source_id is not None:
            managed_paths[source_id] = path

    ensure: list[DesiredSource] = []
    for source_id in sorted(desired_by_id, key=str):
        desired = desired_by_id[source_id]
        configured = managed_paths.get(source_id)
        # Adapter 用 None 表示字段缺失或类型错误。这里使用 ``is not False``，让未知值和 True
        # 都进入 replace；只有两个受管字段都能证明完全一致时才跳过写入。
        if (
            configured is None
            or configured.source_url != desired.source_url
            or configured.source_on_demand is not False
        ):
            ensure.append(desired)

    release = tuple(sorted(managed_paths.keys() - desired_by_id.keys(), key=str))
    return ReconciliationPlan(
        desired_count=len(desired_tuple),
        managed_path_count=len(managed_paths),
        ensure=tuple(ensure),
        release=release,
    )


async def reconcile_once(
    lease: MediaReconciliationLease,
    stream_gateway: StreamGatewayPort,
) -> ReconciliationResult:
    """执行一轮全量对账；快照失败时零写入，单项写失败时继续。

    取消使用 ``BaseException`` 分支之外的自然传播路径，确保应用关闭能立即进入 Lease 的
    ``finally`` 释放 advisory lock。其余错误只转换成稳定分类，不把异常文本带到日志结果。
    """

    try:
        async with lease.acquire() as reader:
            if reader is None:
                return ReconciliationResult(ReconciliationOutcome.SKIPPED_LOCK)

            try:
                # 必须先取得一份完整远端快照。Adapter 只有在所有分页通过校验后才会返回；远端
                # 不可用或快照不完整时在这里终止，本轮既不做无用的数据库读取，也不产生写入。
                remote_snapshot = await stream_gateway.fetch_config_path_snapshot()
            except StreamGatewayUnavailableError:
                return ReconciliationResult(ReconciliationOutcome.GATEWAY_UNAVAILABLE)
            except StreamGatewayInvalidResponseError:
                return ReconciliationResult(ReconciliationOutcome.GATEWAY_INVALID_RESPONSE)
            except asyncio.CancelledError:
                raise
            except Exception:
                return ReconciliationResult(ReconciliationOutcome.UNEXPECTED_ERROR)

            try:
                cameras = await reader.read_all()
                desired_sources = tuple(
                    desired
                    for camera in cameras
                    for desired in build_camera_desired_sources(camera)
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                # Reader、Mapper 或聚合构造任一失败都表示数据库快照不可安全使用。本分支发生
                # 在任何写入之前，因此不会根据部分 Camera 删除或覆盖远端 Path。
                return ReconciliationResult(ReconciliationOutcome.DATABASE_ERROR)

            try:
                plan = calculate_reconciliation_plan(desired_sources, remote_snapshot)
            except Exception:
                return ReconciliationResult(ReconciliationOutcome.UNEXPECTED_ERROR)

            ensured_count = 0
            released_count = 0
            failed_count = 0
            # 先恢复数据库仍需要的 Path，再执行删除性清理；若本轮中途被取消，至少不会先删掉
            # 孤儿再开始恢复。单项失败仍继续，避免一个坏 Source 阻塞其余恢复工作。
            for desired in plan.ensure:
                try:
                    await stream_gateway.ensure_path(desired)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    # Adapter 已负责单次 I/O 分类和脱敏日志。Reconciler 只累计数量，不能记录
                    # DesiredSource 或异常文本，因为两者都可能间接包含上游凭据。
                    failed_count += 1
                else:
                    ensured_count += 1

            for source_id in plan.release:
                try:
                    await stream_gateway.release_path(source_id)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    failed_count += 1
                else:
                    released_count += 1

            return ReconciliationResult(
                outcome=(
                    ReconciliationOutcome.PARTIAL_FAILURE
                    if failed_count
                    else ReconciliationOutcome.SUCCESS
                ),
                desired_count=plan.desired_count,
                managed_path_count=plan.managed_path_count,
                ensured_count=ensured_count,
                released_count=released_count,
                failed_count=failed_count,
            )
    except asyncio.CancelledError:
        raise
    except Exception:
        # 进入/退出 Lease 的连接、锁和 Reader 基础设施都属于数据库边界。
        return ReconciliationResult(ReconciliationOutcome.DATABASE_ERROR)


class MediaReconciliationRunner:
    """启动即执行、轮次不重叠且带失败退避的媒体对账循环。"""

    def __init__(
        self,
        *,
        lease: MediaReconciliationLease,
        stream_gateway: StreamGatewayPort,
        interval_seconds: float,
        max_backoff_seconds: float,
        sleep: Sleep = asyncio.sleep,
        jitter: Jitter = random.uniform,
        monotonic: MonotonicClock = time.monotonic,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("媒体对账周期必须大于 0。")
        if max_backoff_seconds < interval_seconds:
            raise ValueError("媒体对账最大退避不能小于正常周期。")
        self._lease = lease
        self._stream_gateway = stream_gateway
        self._interval_seconds = interval_seconds
        self._max_backoff_seconds = max_backoff_seconds
        self._sleep = sleep
        self._jitter = jitter
        self._monotonic = monotonic

    async def run_forever(self) -> None:
        """顺序执行无限轮次；取消不记录成故障，也不启动下一轮。"""

        consecutive_failures = 0
        while True:
            started_at = self._monotonic()
            try:
                result = await reconcile_once(self._lease, self._stream_gateway)
            except asyncio.CancelledError:
                raise
            except Exception:
                # reconcile_once 已防御普通异常；这里仍保护长期任务不因未来回归静默退出。
                result = ReconciliationResult(ReconciliationOutcome.UNEXPECTED_ERROR)

            if result.is_failure:
                consecutive_failures += 1
                # failure_count=1 对应 interval×2；随后在 50%～100% 范围抖动。也就是说首次
                # 故障不会比正常轮询更频繁，同时多个实例不会在同一时刻持续撞向故障依赖。
                backoff = self._failure_backoff(consecutive_failures)
                next_delay = self._jitter(backoff * 0.5, backoff)
            else:
                consecutive_failures = 0
                next_delay = self._interval_seconds

            self._log_round(
                result=result,
                duration_ms=max(0, round((self._monotonic() - started_at) * 1000)),
                next_delay_seconds=next_delay,
            )
            await self._sleep(next_delay)

    def _failure_backoff(self, failure_count: int) -> float:
        """逐次翻倍并在达到上限后停止计算，避免长期故障产生巨大指数。"""

        backoff = self._interval_seconds
        for _ in range(failure_count):
            backoff = min(backoff * 2, self._max_backoff_seconds)
            if backoff == self._max_backoff_seconds:
                break
        return backoff

    @staticmethod
    def _log_round(
        *,
        result: ReconciliationResult,
        duration_ms: int,
        next_delay_seconds: float,
    ) -> None:
        """每轮只记录脱敏汇总；extra 字段便于日志采集与确定性测试。"""

        trace_id = get_trace_id() or "-"
        extra = {
            "operation": "media_reconciliation",
            "outcome": result.outcome.value,
            "duration_ms": duration_ms,
            "desired_count": result.desired_count,
            "managed_path_count": result.managed_path_count,
            "ensured_count": result.ensured_count,
            "released_count": result.released_count,
            "failed_count": result.failed_count,
            "next_delay_seconds": next_delay_seconds,
            "trace_id": trace_id,
        }
        level = logging.INFO if not result.is_failure else logging.WARNING
        logger.log(
            level,
            (
                "media_reconciliation operation=media_reconciliation outcome=%s "
                "duration_ms=%d desired_count=%d managed_path_count=%d ensured_count=%d "
                "released_count=%d failed_count=%d next_delay_seconds=%.3f trace_id=%s"
            ),
            result.outcome.value,
            duration_ms,
            result.desired_count,
            result.managed_path_count,
            result.ensured_count,
            result.released_count,
            result.failed_count,
            next_delay_seconds,
            trace_id,
            extra=extra,
        )
