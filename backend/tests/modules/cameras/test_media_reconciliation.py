"""媒体差异、单轮协调、失败退避和取消的框架无关测试。"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

import pytest

import app.modules.cameras.application.reconciliation as reconciliation_module
from app.modules.cameras.application.media import build_camera_desired_sources
from app.modules.cameras.application.ports import CameraMediaStateReader
from app.modules.cameras.application.reconciliation import (
    MediaReconciliationRunner,
    ReconciliationOutcome,
    ReconciliationResult,
    calculate_reconciliation_plan,
    reconcile_once,
)
from app.modules.cameras.domain import Camera, CameraSourceChange
from app.modules.stream_gateway.ports import (
    ConfiguredPath,
    ConfiguredPathSnapshot,
    DesiredSource,
    RuntimePathSnapshot,
    StreamGatewayInvalidResponseError,
    StreamGatewayUnavailableError,
)
from tests.modules.cameras.builders import (
    CameraBuilder,
    FixedClock,
    FixedIdGenerator,
    uuid4_from_index,
)
from tests.modules.cameras.constants import CAMERA_LEAK_SENTINEL

pytestmark = pytest.mark.anyio

CHECKED_AT = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)
SOURCE_A = uuid4_from_index(10)
SOURCE_B = uuid4_from_index(20)
SOURCE_C = uuid4_from_index(30)
SOURCE_D = uuid4_from_index(40)


def configured_snapshot(*paths: ConfiguredPath) -> ConfiguredPathSnapshot:
    """用固定 UTC 时间构造完整远端配置快照。"""

    return ConfiguredPathSnapshot(paths=paths, checked_at=CHECKED_AT)


class FakeReader:
    """记录全量读取次数，并可模拟数据库/Mapper 失败。"""

    def __init__(self, cameras: tuple[Camera, ...] = (), error: Exception | None = None) -> None:
        self.cameras = cameras
        self.error = error
        self.read_count = 0

    async def read_all(self) -> tuple[Camera, ...]:
        self.read_count += 1
        if self.error is not None:
            raise self.error
        return self.cameras


class FakeLease:
    """提供可控 Reader 或锁竞争结果，并记录所有退出路径。"""

    def __init__(self, reader: CameraMediaStateReader | None) -> None:
        self.reader = reader
        self.enter_count = 0
        self.exit_count = 0

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[CameraMediaStateReader | None]:
        self.enter_count += 1
        try:
            yield self.reader
        finally:
            self.exit_count += 1


class FakeStreamGateway:
    """保存远端配置并记录确定性的 ensure/release 顺序。"""

    def __init__(self, snapshot: ConfiguredPathSnapshot) -> None:
        self.configured = {path.name: path for path in snapshot.paths}
        self.snapshot_error: Exception | None = None
        self.fetch_count = 0
        self.operations: list[tuple[str, UUID]] = []
        self.fail_ensure: set[UUID] = set()
        self.fail_release: set[UUID] = set()

    async def fetch_config_path_snapshot(self) -> ConfiguredPathSnapshot:
        self.fetch_count += 1
        if self.snapshot_error is not None:
            raise self.snapshot_error
        return configured_snapshot(*self.configured.values())

    async def ensure_path(self, desired_source: DesiredSource) -> None:
        self.operations.append(("ensure", desired_source.source_id))
        if desired_source.source_id in self.fail_ensure:
            raise StreamGatewayUnavailableError
        self.configured[desired_source.path_name] = ConfiguredPath(
            name=desired_source.path_name,
            source_url=desired_source.source_url,
            source_on_demand=False,
        )

    async def release_path(self, source_id: UUID) -> None:
        self.operations.append(("release", source_id))
        if source_id in self.fail_release:
            raise StreamGatewayUnavailableError
        self.configured.pop(str(source_id), None)

    async def fetch_runtime_path_snapshot(self) -> RuntimePathSnapshot:
        raise AssertionError("媒体对账不应读取运行态 Path")

    def whep_url_for(self, source_id: UUID) -> str:
        raise AssertionError(f"媒体对账不应构造 WHEP URL：{source_id}")


def desired(source_id: UUID, suffix: str) -> DesiredSource:
    return DesiredSource(source_id=source_id, source_url=f"rtsp://camera.invalid/{suffix}")


def test_calculate_plan_covers_missing_drift_orphan_and_unmanaged_paths() -> None:
    """三个集合互斥、按 Source ID 排序，非受管 Path 完全忽略。"""

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
def test_calculate_plan_treats_unknown_or_true_managed_fields_as_drift(
    configured: ConfiguredPath,
) -> None:
    """无法证明完全相等的受管 Path 必须由 replace 恢复。"""

    target = desired(SOURCE_A, "a")
    plan = calculate_reconciliation_plan((target,), configured_snapshot(configured))
    assert plan.ensure == (target,)


async def test_lock_competition_skips_both_snapshots_and_writes() -> None:
    """未取得 Lease 不读取数据库或 MediaMTX，并按正常调度结果返回。"""

    gateway = FakeStreamGateway(configured_snapshot())
    lease = FakeLease(None)

    result = await reconcile_once(lease, gateway)

    assert result.outcome is ReconciliationOutcome.SKIPPED_LOCK
    assert gateway.fetch_count == 0
    assert gateway.operations == []
    assert lease.exit_count == 1


@pytest.mark.parametrize(
    ("error", "outcome"),
    [
        (StreamGatewayUnavailableError(), ReconciliationOutcome.GATEWAY_UNAVAILABLE),
        (StreamGatewayInvalidResponseError(), ReconciliationOutcome.GATEWAY_INVALID_RESPONSE),
    ],
)
async def test_gateway_snapshot_failure_is_zero_write_and_precedes_database_read(
    error: Exception,
    outcome: ReconciliationOutcome,
) -> None:
    """不完整远端快照不能触发删除或覆盖，也无需再读取数据库。"""

    reader = FakeReader((CameraBuilder().build(source_count=1),))
    lease = FakeLease(reader)
    gateway = FakeStreamGateway(configured_snapshot())
    gateway.snapshot_error = error

    result = await reconcile_once(lease, gateway)

    assert result.outcome is outcome
    assert reader.read_count == 0
    assert gateway.operations == []


async def test_database_or_aggregate_failure_is_zero_write() -> None:
    """远端快照成功后，数据库全量读取失败仍必须放弃整轮。"""

    reader = FakeReader(error=RuntimeError("数据库测试故障"))
    gateway = FakeStreamGateway(
        configured_snapshot(ConfiguredPath(str(SOURCE_D), "rtsp://camera.invalid/orphan", False))
    )

    result = await reconcile_once(FakeLease(reader), gateway)

    assert result.outcome is ReconciliationOutcome.DATABASE_ERROR
    assert reader.read_count == 1
    assert gateway.operations == []


async def test_partial_write_failure_continues_ensure_then_release_in_order() -> None:
    """单项失败不阻断其余项，且全部 ensure 始终先于孤儿 release。"""

    camera = CameraBuilder().build(source_count=2, id_start=9)
    first_id, second_id = (source.source_id for source in camera.sources)
    orphan_id = uuid4_from_index(99)
    gateway = FakeStreamGateway(
        configured_snapshot(ConfiguredPath(str(orphan_id), "rtsp://camera.invalid/orphan", False))
    )
    gateway.fail_ensure.add(first_id)
    gateway.fail_release.add(orphan_id)

    result = await reconcile_once(FakeLease(FakeReader((camera,))), gateway)

    assert gateway.operations == [
        ("ensure", first_id),
        ("ensure", second_id),
        ("release", orphan_id),
    ]
    assert result == ReconciliationResult(
        outcome=ReconciliationOutcome.PARTIAL_FAILURE,
        desired_count=2,
        managed_path_count=1,
        ensured_count=1,
        released_count=0,
        failed_count=2,
    )


async def test_next_full_round_recovers_and_then_performs_no_duplicate_writes() -> None:
    """清空远端后完整恢复；下一轮重新取双方快照并成为无写入成功。"""

    camera = CameraBuilder().build(source_count=2)
    reader = FakeReader((camera,))
    gateway = FakeStreamGateway(configured_snapshot())
    lease = FakeLease(reader)

    first = await reconcile_once(lease, gateway)
    operations_after_first = tuple(gateway.operations)
    second = await reconcile_once(lease, gateway)

    assert first.outcome is ReconciliationOutcome.SUCCESS
    assert first.ensured_count == 2
    assert tuple(operation for operation, _ in operations_after_first) == ("ensure", "ensure")
    assert second == ReconciliationResult(
        outcome=ReconciliationOutcome.SUCCESS,
        desired_count=2,
        managed_path_count=2,
    )
    assert tuple(gateway.operations) == operations_after_first
    assert reader.read_count == 2
    assert gateway.fetch_count == 2


async def test_later_round_restores_latest_database_change_and_releases_late_orphan() -> None:
    """快照后的数据库变化允许短暂旧写；下一轮使用最新配置，删除后再下一轮清理孤儿。"""

    builder = CameraBuilder()
    camera = builder.build(source_count=1)
    source = camera.sources[0]
    reader = FakeReader((camera,))
    gateway = FakeStreamGateway(configured_snapshot())
    lease = FakeLease(reader)
    first = await reconcile_once(lease, gateway)
    assert first.ensured_count == 1

    builder.clock.set(camera.updated_at.replace(microsecond=1))
    updated = camera.update_configuration(
        name=camera.name,
        ip_address=camera.ip_address,
        rtsp_port=camera.rtsp_port,
        username=camera.credentials.username,
        password=camera.credentials.password.reveal(),
        sources=(
            CameraSourceChange(
                source_id=source.source_id,
                name=source.name,
                url_suffix="Streaming/Channels/999",
                is_default_preview=True,
            ),
        ),
        id_generator=FixedIdGenerator(()),
        clock=FixedClock(camera.updated_at.replace(microsecond=1)),
    )
    reader.cameras = (updated,)
    second = await reconcile_once(lease, gateway)
    assert second.ensured_count == 1
    assert gateway.configured[str(source.source_id)].source_url.endswith("/Streaming/Channels/999")

    # 模拟数据库删除已提交但即时媒体清理尚未执行；后台恢复必须在后续轮次删除同名 Path。
    reader.cameras = ()
    third = await reconcile_once(lease, gateway)
    assert third.released_count == 1
    assert gateway.configured == {}


async def test_cancellation_propagates_after_lease_exit() -> None:
    """应用关闭取消正在读取的远端快照时，Lease finally 必须先执行。"""

    entered = asyncio.Event()

    class BlockingGateway(FakeStreamGateway):
        async def fetch_config_path_snapshot(self) -> ConfiguredPathSnapshot:
            entered.set()
            await asyncio.Event().wait()
            raise AssertionError("阻塞快照只能通过取消退出")

    lease = FakeLease(FakeReader())
    task = asyncio.create_task(reconcile_once(lease, BlockingGateway(configured_snapshot())))
    await entered.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert lease.exit_count == 1


async def test_runner_uses_exponential_jitter_and_resets_after_success(monkeypatch) -> None:
    """失败翻倍并抖动，成功和锁竞争都恢复正常周期。"""

    results = iter(
        (
            ReconciliationResult(ReconciliationOutcome.DATABASE_ERROR),
            ReconciliationResult(ReconciliationOutcome.PARTIAL_FAILURE),
            ReconciliationResult(ReconciliationOutcome.SUCCESS),
            ReconciliationResult(ReconciliationOutcome.SKIPPED_LOCK),
        )
    )

    async def fake_reconcile_once(_lease, _gateway) -> ReconciliationResult:
        return next(results)

    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)
        if len(delays) == 4:
            raise asyncio.CancelledError

    monkeypatch.setattr(reconciliation_module, "reconcile_once", fake_reconcile_once)
    runner = MediaReconciliationRunner(
        lease=object(),  # type: ignore[arg-type]
        stream_gateway=object(),  # type: ignore[arg-type]
        interval_seconds=30,
        max_backoff_seconds=300,
        sleep=record_sleep,
        jitter=lambda lower, upper: (lower + upper) / 2,
    )

    with pytest.raises(asyncio.CancelledError):
        await runner.run_forever()

    assert delays == [45, 90, 30, 30]


async def test_runner_summary_log_does_not_contain_credentials_or_full_urls(caplog) -> None:
    """即使本轮 Desired State 含测试密码，汇总日志也只输出数量与稳定分类。"""

    camera = CameraBuilder().build(source_count=1)
    gateway = FakeStreamGateway(configured_snapshot())
    lease = FakeLease(FakeReader((camera,)))

    async def stop_after_first(_delay: float) -> None:
        raise asyncio.CancelledError

    runner = MediaReconciliationRunner(
        lease=lease,
        stream_gateway=gateway,
        interval_seconds=30,
        max_backoff_seconds=300,
        sleep=stop_after_first,
    )
    with caplog.at_level(logging.DEBUG), pytest.raises(asyncio.CancelledError):
        await runner.run_forever()

    desired_url = build_camera_desired_sources(camera)[0].source_url
    record = next(
        record for record in caplog.records if record.name == reconciliation_module.__name__
    )
    assert record.event == "media_reconciliation.round_completed"
    assert record.message == "媒体对账完成"
    assert record.levelno == logging.INFO
    assert not hasattr(record, "trace_id")
    assert CAMERA_LEAK_SENTINEL not in caplog.text
    assert desired_url not in caplog.text


async def run_logged_results(
    monkeypatch,
    caplog,
    results: tuple[ReconciliationResult, ...],
    ended_at: tuple[float, ...],
) -> tuple[list[logging.LogRecord], list[float]]:
    """用指定轮次结果和结束时刻驱动 Runner，避免降噪测试依赖真实时间。"""

    result_iterator = iter(results)

    async def fake_reconcile_once(_lease, _gateway) -> ReconciliationResult:
        return next(result_iterator)

    delays: list[float] = []

    async def stop_after_results(delay: float) -> None:
        delays.append(delay)
        if len(delays) == len(results):
            raise asyncio.CancelledError

    # 每轮各读取一次开始和结束时刻。开始值与结束值相同，让 duration 固定为 0，并把测试注意力
    # 放在跨轮提醒时间而非单轮运行耗时。
    monotonic_values = iter(value for end in ended_at for value in (end, end))
    monkeypatch.setattr(reconciliation_module, "reconcile_once", fake_reconcile_once)
    runner = MediaReconciliationRunner(
        lease=object(),  # type: ignore[arg-type]
        stream_gateway=object(),  # type: ignore[arg-type]
        interval_seconds=30,
        max_backoff_seconds=300,
        sleep=stop_after_results,
        jitter=lambda _lower, upper: upper,
        monotonic=lambda: next(monotonic_values),
    )

    with caplog.at_level(logging.DEBUG, logger=reconciliation_module.__name__):
        with pytest.raises(asyncio.CancelledError):
            await runner.run_forever()

    records = [record for record in caplog.records if record.name == reconciliation_module.__name__]
    return records, delays


async def test_repeated_failure_warns_once_and_keeps_backoff_behavior(
    monkeypatch,
    caplog,
) -> None:
    """七轮同类故障仅首次为 WARNING，其余 DEBUG，同时保留原退避上限。"""

    records, delays = await run_logged_results(
        monkeypatch,
        caplog,
        tuple(ReconciliationResult(ReconciliationOutcome.GATEWAY_UNAVAILABLE) for _ in range(7)),
        tuple(float(index) for index in range(7)),
    )

    assert [record.levelno for record in records] == [logging.WARNING] + [logging.DEBUG] * 6
    assert {record.event for record in records} == {"media_reconciliation.round_failed"}
    assert {record.message for record in records} == {"MediaMTX 不可用，本轮对账已跳过"}
    assert [record.consecutive_failures for record in records] == list(range(1, 8))
    assert all(not hasattr(record, "desired_count") for record in records)
    assert all(not hasattr(record, "trace_id") for record in records)
    assert delays == [60, 120, 240, 300, 300, 300, 300]


async def test_failure_change_reminder_and_recovery_use_one_degradation_state(
    monkeypatch,
    caplog,
) -> None:
    """类型变化立即告警，30 分钟提醒重新计时，成功只输出一条恢复事件。"""

    success = ReconciliationResult(
        ReconciliationOutcome.SUCCESS,
        desired_count=4,
        managed_path_count=4,
        ensured_count=0,
        released_count=0,
    )
    records, _ = await run_logged_results(
        monkeypatch,
        caplog,
        (
            ReconciliationResult(ReconciliationOutcome.GATEWAY_UNAVAILABLE),
            ReconciliationResult(ReconciliationOutcome.GATEWAY_UNAVAILABLE),
            ReconciliationResult(ReconciliationOutcome.GATEWAY_UNAVAILABLE),
            ReconciliationResult(ReconciliationOutcome.DATABASE_ERROR),
            ReconciliationResult(ReconciliationOutcome.DATABASE_ERROR),
            success,
        ),
        (0.0, 1799.0, 1800.0, 1801.0, 3601.0, 3602.0),
    )

    assert [record.levelno for record in records] == [
        logging.WARNING,
        logging.DEBUG,
        logging.WARNING,
        logging.WARNING,
        logging.WARNING,
        logging.INFO,
    ]
    recovered = records[-1]
    assert recovered.event == "media_reconciliation.recovered"
    assert recovered.message == "数据库已恢复，对账完成"
    assert recovered.outcome == "success"
    assert recovered.consecutive_failures == 5
    assert recovered.degraded_duration_seconds == 3602.0
    assert recovered.ensured_count == 0
    assert recovered.released_count == 0
    assert sum(record.event == "media_reconciliation.recovered" for record in records) == 1


async def test_skipped_lock_does_not_clear_failure_state_or_count_as_recovery(
    monkeypatch,
    caplog,
) -> None:
    """锁竞争只记录 DEBUG；后续真实成功才报告包含实际失败轮数的恢复。"""

    records, delays = await run_logged_results(
        monkeypatch,
        caplog,
        (
            ReconciliationResult(ReconciliationOutcome.GATEWAY_INVALID_RESPONSE),
            ReconciliationResult(ReconciliationOutcome.SKIPPED_LOCK),
            ReconciliationResult(
                ReconciliationOutcome.SUCCESS,
                desired_count=2,
                managed_path_count=2,
            ),
        ),
        (10.0, 20.0, 30.0),
    )

    assert [record.event for record in records] == [
        "media_reconciliation.round_failed",
        "media_reconciliation.round_completed",
        "media_reconciliation.recovered",
    ]
    assert records[1].message == "未取得对账锁，本轮已跳过"
    assert records[1].levelno == logging.DEBUG
    assert records[2].message == "MediaMTX 已恢复，对账完成"
    assert records[2].consecutive_failures == 1
    assert records[2].degraded_duration_seconds == 20.0
    # 锁竞争继续按原逻辑清空退避，因此 success 前后的 sleep 都是正常周期。
    assert delays == [60, 30, 30]


async def test_success_levels_and_partial_failure_fields_follow_event_table(
    monkeypatch,
    caplog,
) -> None:
    """无变更成功为 DEBUG，有写入为 INFO；只有部分失败携带五个计数字段。"""

    records, _ = await run_logged_results(
        monkeypatch,
        caplog,
        (
            ReconciliationResult(
                ReconciliationOutcome.SUCCESS,
                desired_count=2,
                managed_path_count=2,
            ),
            ReconciliationResult(
                ReconciliationOutcome.SUCCESS,
                desired_count=2,
                managed_path_count=1,
                ensured_count=1,
            ),
            ReconciliationResult(
                ReconciliationOutcome.PARTIAL_FAILURE,
                desired_count=2,
                managed_path_count=1,
                ensured_count=1,
                released_count=0,
                failed_count=1,
            ),
        ),
        (0.0, 1.0, 2.0),
    )

    assert [record.levelno for record in records] == [
        logging.DEBUG,
        logging.INFO,
        logging.WARNING,
    ]
    assert not hasattr(records[0], "ensured_count")
    assert records[1].ensured_count == 1
    assert records[1].released_count == 0
    assert records[2].desired_count == 2
    assert records[2].managed_path_count == 1
    assert records[2].ensured_count == 1
    assert records[2].released_count == 0
    assert records[2].failed_count == 1
