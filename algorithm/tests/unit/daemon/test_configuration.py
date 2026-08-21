from datetime import UTC, datetime
from pathlib import Path

import pytest

from algorithm.daemon.configuration import WorkerConfigurationError, validate_record
from algorithm.daemon.registry import get_worker_definition
from algorithm.database import TaskParameterRecord
from algorithm.workers.detector.config import DetectorConfig


def record(*, confidence: float = 0.5) -> TaskParameterRecord:
    return TaskParameterRecord(
        task_id="detector-001",
        worker_type="detector",
        config={
            "camera_id": "camera-001",
            "source_id": "source-001",
            "rtsp_url": "rtsp://user:secret@camera/stream",
            "redis_url": "redis://user:secret@localhost/0",
            "model_path": "models/model.pt",
            "confidence": confidence,
        },
        updated_at=datetime(2026, 8, 21, tzinfo=UTC),
    )


def test_validates_record_and_resolves_model_relative_to_resource_root(
    tmp_path: Path,
) -> None:
    loaded = validate_record(record(), tmp_path)

    assert isinstance(loaded.config, DetectorConfig)
    assert loaded.config.task_id == "detector-001"
    assert loaded.config.model_path == (tmp_path / "models/model.pt").resolve()
    assert loaded.revision.startswith("sha256:")


def test_revision_changes_with_worker_parameters(tmp_path: Path) -> None:
    first = validate_record(record(confidence=0.5), tmp_path).revision
    second = validate_record(record(confidence=0.7), tmp_path).revision
    assert first != second


def test_validation_error_does_not_echo_credentials(tmp_path: Path) -> None:
    with pytest.raises(WorkerConfigurationError) as captured:
        validate_record(record(confidence=2), tmp_path)
    assert "secret" not in str(captured.value)
    assert "confidence" in str(captured.value)


def test_public_schema_excludes_task_id_and_contains_nested_roi() -> None:
    schema = get_worker_definition("detector").parameter_schema()
    assert "task_id" not in schema["properties"]
    assert "task_id" not in schema["required"]
    assert schema["properties"]["confidence"]["default"] == 0.5
    assert "RoiConfig" in schema["$defs"]
