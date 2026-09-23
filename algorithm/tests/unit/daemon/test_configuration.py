from datetime import UTC, datetime
from pathlib import Path

import pytest

from algorithm.common.config import AlgorithmConfig, WorkerModelConfig
from algorithm.daemon.configuration import WorkerConfigurationError, validate_record
from algorithm.daemon.registry import get_worker_definition
from algorithm.database import TaskParameterRecord
from algorithm.workers.detector.config import DetectorConfig
from algorithm.workers.config import VideoWorkerConfig
from algorithm.workers.tracker.config import TrackerConfig


def record(*, confidence: float = 0.5) -> TaskParameterRecord:
    return TaskParameterRecord(
        task_id="detector-001",
        worker_type="detector",
        config={
            "rtsp_url": "rtsp://user:secret@camera/stream",
            "confidence": confidence,
        },
        updated_at=datetime(2026, 8, 21, tzinfo=UTC),
    )


def outer_config(
    tmp_path: Path,
    *,
    redis_url: str = "redis://outer/0",
) -> AlgorithmConfig:
    return AlgorithmConfig(
        redis_url=redis_url,
        workers={
            "detector": WorkerModelConfig(
                model_path=tmp_path / "models/detector.pt"
            ),
            "tracker": WorkerModelConfig(model_path=tmp_path / "models/tracker.pt"),
        },
    )


def test_任务参数与toml配置合并为worker运行配置(
    tmp_path: Path,
) -> None:
    loaded = validate_record(record(), outer_config(tmp_path))

    assert isinstance(loaded.config, DetectorConfig)
    assert loaded.config.task_id == "detector-001"
    assert loaded.config.redis_url == "redis://outer/0"
    assert loaded.config.model_path == tmp_path / "models/detector.pt"
    assert loaded.revision.startswith("sha256:")


@pytest.mark.parametrize("field", ["redis_url", "model_path"])
def test_任务参数包含外围配置字段时拒绝启动(
    tmp_path: Path,
    field: str,
) -> None:
    task = record()
    task = TaskParameterRecord(
        task_id=task.task_id,
        worker_type=task.worker_type,
        config={**task.config, field: "不应写入任务"},
        updated_at=task.updated_at,
    )

    with pytest.raises(WorkerConfigurationError) as captured:
        validate_record(task, outer_config(tmp_path))

    assert field in str(captured.value)


def test_revision_changes_with_worker_parameters(tmp_path: Path) -> None:
    config = outer_config(tmp_path)
    first = validate_record(record(confidence=0.5), config).revision
    second = validate_record(record(confidence=0.7), config).revision
    assert first != second


def test_revision_changes_with_outer_config(tmp_path: Path) -> None:
    first = validate_record(
        record(), outer_config(tmp_path, redis_url="redis://first/0")
    ).revision
    second = validate_record(
        record(), outer_config(tmp_path, redis_url="redis://second/0")
    ).revision
    assert first != second


def test_validation_error_does_not_echo_credentials(tmp_path: Path) -> None:
    with pytest.raises(WorkerConfigurationError) as captured:
        validate_record(record(confidence=2), outer_config(tmp_path))
    assert "secret" not in str(captured.value)
    assert "confidence" in str(captured.value)


def test_public_schema_excludes_task_id_and_contains_nested_roi() -> None:
    schema = get_worker_definition("detector").parameter_schema()
    assert "task_id" not in schema["properties"]
    assert "task_id" not in schema["required"]
    assert "redis_url" not in schema["properties"]
    assert "model_path" not in schema["properties"]
    assert "redis_url" not in schema["required"]
    assert "model_path" not in schema["required"]
    assert not {
        "camera_id",
        "source_id",
        "algorithm_id",
        "algorithm_version",
    } & schema["properties"].keys()
    assert schema["properties"]["confidence"]["default"] == 0.5
    assert "RoiConfig" in schema["$defs"]


def test_worker_configs_share_base_without_referencing_each_other() -> None:
    detector_schema = get_worker_definition("detector").parameter_schema()
    tracker_schema = get_worker_definition("tracker").parameter_schema()

    assert issubclass(DetectorConfig, VideoWorkerConfig)
    assert issubclass(TrackerConfig, VideoWorkerConfig)
    assert not issubclass(TrackerConfig, DetectorConfig)
    assert detector_schema["properties"] == tracker_schema["properties"]
    assert detector_schema["title"] == "DetectorConfig"
    assert tracker_schema["title"] == "TrackerConfig"
    assert "task_id" not in tracker_schema["properties"]
    assert "tracker_config_path" not in tracker_schema["properties"]

    tracker_record = TaskParameterRecord(
        task_id="tracker-001",
        worker_type="tracker",
        config=record().config,
        updated_at=datetime(2026, 8, 21, tzinfo=UTC),
    )
    loaded = validate_record(tracker_record, outer_config(Path("/resources")))
    assert isinstance(loaded.config, TrackerConfig)
    assert loaded.config.model_path == Path("/resources/models/tracker.pt")
