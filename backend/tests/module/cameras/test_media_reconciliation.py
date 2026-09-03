"""媒体单轮对账、周期 Runner、失败退避和取消的模块协作测试。"""

import asyncio
import logging
from datetime import UTC, datetime

import pytest

import app.modules.cameras.application.reconciliation as reconciliation_module
from app.modules.cameras.application.media import build_camera_desired_sources
from app.modules.cameras.application.reconciliation import (
    MediaReconciliationRunner,
    ReconciliationOutcome,
    ReconciliationResult,
    reconcile_once,
)
from app.modules.cameras.domain import CameraSourceChange
from app.modules.stream_gateway.ports import (
    ConfiguredPath,
    ConfiguredPathSnapshot,
    StreamGatewayInvalidResponseError,
    StreamGatewayUnavailableError,
)
from tests.support.cameras.builders import (
    CameraBuilder,
    FixedClock,
    FixedIdGenerator,
    uuid4_from_index,
)
from tests.support.cameras.constants import CAMERA_LEAK_SENTINEL
from tests.support.cameras.fakes import (
    FakeMediaReconciliationLease,
    FakeMediaStateReader,
    FakeReconciliationStreamGateway,
)

pytestmark = pytest.mark.anyio

CHECKED_AT = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)
SOURCE_D = uuid4_from_index(40)


def configured_snapshot(*paths: ConfiguredPath) -> ConfiguredPathSnapshot:
    """用固定 UTC 时间构造完整远端配置快照。"""

    return ConfiguredPathSnapshot(paths=paths, checked_at=CHECKED_AT)


async def test_锁竞争时跳过两侧快照和写操作() -> None:
    """未取得 Lease 不读取数据库或 MediaMTX，并按正常调度结果返回。"""

    gateway = FakeReconciliationStreamGateway(configured_snapshot())
    lease = FakeMediaReconciliationLease(None)

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
async def test_网关快照失败时不写入且发生在数据库读取前(
    error: Exception,
    outcome: ReconciliationOutcome,
) -> None:
    """不完整远端快照不能触发删除或覆盖，也无需再读取数据库。"""

    reader = FakeMediaStateReader((CameraBuilder().build(source_count=1),))
    lease = FakeMediaReconciliationLease(reader)
    gateway = FakeReconciliationStreamGateway(configured_snapshot())
    gateway.snapshot_error = error

    result = await reconcile_once(lease, gateway)

    assert result.outcome is outcome
    assert reader.read_count == 0
    assert gateway.operations == []


async def test_数据库或聚合失败时不执行写操作() -> None:
    """远端快照成功后，数据库全量读取失败仍必须放弃整轮。"""

    reader = FakeMediaStateReader(error=RuntimeError("数据库测试故障"))
    gateway = FakeReconciliationStreamGateway(
        configured_snapshot(ConfiguredPath(str(SOURCE_D), "rtsp://camera.invalid/orphan", False))
    )

    result = await reconcile_once(FakeMediaReconciliationLease(reader), gateway)

    assert result.outcome is ReconciliationOutcome.DATABASE_ERROR
    assert reader.read_count == 1
    assert gateway.operations == []


async def test_部分写入失败时继续按顺序确保和释放() -> None:
    """单项失败不阻断其余项，且全部 ensure 始终先于孤儿 release。"""

    camera = CameraBuilder().build(source_count=2, id_start=9)
    first_id, second_id = (source.source_id for source in camera.sources)
    orphan_id = uuid4_from_index(99)
    gateway = FakeReconciliationStreamGateway(
        configured_snapshot(ConfiguredPath(str(orphan_id), "rtsp://camera.invalid/orphan", False))
    )
    gateway.ensure_failures[first_id] = StreamGatewayUnavailableError()
    gateway.release_failures[orphan_id] = StreamGatewayUnavailableError()

    result = await reconcile_once(
        FakeMediaReconciliationLease(FakeMediaStateReader((camera,))), gateway
    )

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


async def test_下一轮完整对账恢复后不执行重复写入() -> None:
    """清空远端后完整恢复；下一轮重新取双方快照并成为无写入成功。"""

    camera = CameraBuilder().build(source_count=2)
    reader = FakeMediaStateReader((camera,))
    gateway = FakeReconciliationStreamGateway(configured_snapshot())
    lease = FakeMediaReconciliationLease(reader)

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


async def test_后续对账恢复最新数据库变更并释放迟到的孤儿资源() -> None:
    """快照后的数据库变化允许短暂旧写；下一轮使用最新配置，删除后再下一轮清理孤儿。"""

    builder = CameraBuilder()
    camera = builder.build(source_count=1)
    source = camera.sources[0]
    reader = FakeMediaStateReader((camera,))
    gateway = FakeReconciliationStreamGateway(configured_snapshot())
    lease = FakeMediaReconciliationLease(reader)
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
    assert gateway.configured_paths[str(source.source_id)].source_url.endswith(
        "/Streaming/Channels/999"
    )

    # 模拟数据库删除已提交但即时媒体清理尚未执行；后台恢复必须在后续轮次删除同名 Path。
    reader.cameras = ()
    third = await reconcile_once(lease, gateway)
    assert third.released_count == 1
    assert gateway.configured_paths == {}


async def test_租约退出后继续抛出取消异常() -> None:
    """应用关闭取消正在读取的远端快照时，Lease finally 必须先执行。"""

    entered = asyncio.Event()

    class BlockingGateway(FakeReconciliationStreamGateway):
        async def fetch_config_path_snapshot(self) -> ConfiguredPathSnapshot:
            entered.set()
            await asyncio.Event().wait()
            raise AssertionError("阻塞快照只能通过取消退出")

    lease = FakeMediaReconciliationLease(FakeMediaStateReader())
    task = asyncio.create_task(reconcile_once(lease, BlockingGateway(configured_snapshot())))
    await entered.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert lease.exit_count == 1


async def test_运行器使用指数抖动并在成功后重置(monkeypatch) -> None:
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


async def test_运行器摘要日志不包含凭据或完整地址(caplog) -> None:
    """即使本轮 Desired State 含测试密码，汇总日志也只输出数量与稳定分类。"""

    camera = CameraBuilder().build(source_count=1)
    gateway = FakeReconciliationStreamGateway(configured_snapshot())
    lease = FakeMediaReconciliationLease(FakeMediaStateReader((camera,)))

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


async def test_重复失败只警告一次并保持退避行为(
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


async def test_失败变化提醒和恢复共用一个降级状态(
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


async def test_跳过锁竞争不清除失败状态也不计为恢复(
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


async def test_成功日志级别和部分失败字段遵循事件表(
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
