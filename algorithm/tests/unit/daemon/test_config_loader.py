import json
from pathlib import Path

import pytest

from algorithm.daemon.config_loader import ConfigLoadError, load_config
from algorithm.workers.detector.config import DetectorConfig


def valid_document(*, confidence: float = 0.5) -> dict:
    return {
        "schema_version": 1,
        "workers": {
            "detector-001": {
                "type": "detector",
                "config": {
                    "camera_id": "camera-001",
                    "source_id": "source-001",
                    "rtsp_url": "rtsp://user:secret@camera/stream",
                    "redis_url": "redis://user:secret@localhost/0",
                    "model_path": "models/model.pt",
                    "confidence": confidence,
                    "roi": {
                        "roi_id": "main",
                        "points": [[0, 0], [1, 0], [1, 1], [0, 1]],
                    },
                },
            }
        },
    }


def write_document(path: Path, document: dict) -> None:
    path.write_text(json.dumps(document), encoding="utf-8")


def test_loads_complete_config_and_resolves_model_relative_to_file(tmp_path) -> None:
    path = tmp_path / "config.json"
    write_document(path, valid_document())

    loaded = load_config(path).workers["detector-001"]

    assert isinstance(loaded.config, DetectorConfig)
    assert loaded.config.task_id == "detector-001"
    assert loaded.config.model_path == (tmp_path / "models/model.pt").resolve()
    assert loaded.config.roi is not None
    assert loaded.revision.startswith("sha256:")


def test_revision_changes_with_worker_parameters(tmp_path) -> None:
    path = tmp_path / "config.json"
    write_document(path, valid_document(confidence=0.5))
    first = load_config(path).workers["detector-001"].revision
    write_document(path, valid_document(confidence=0.7))
    second = load_config(path).workers["detector-001"].revision

    assert first != second


@pytest.mark.parametrize(
    "mutation",
    [
        lambda document: document.update({"unknown": True}),
        lambda document: document["workers"]["detector-001"]["config"].update(
            {"task_id": "duplicated"}
        ),
        lambda document: document["workers"]["detector-001"]["config"].update(
            {"unexpected": True}
        ),
        lambda document: document["workers"]["detector-001"]["config"].update(
            {"roi": {"roi_id": "main", "points": [[0, 0], [1, 0]]}}
        ),
    ],
)
def test_rejects_invalid_complete_configuration(tmp_path, mutation) -> None:
    path = tmp_path / "config.json"
    document = valid_document()
    mutation(document)
    write_document(path, document)

    with pytest.raises(ConfigLoadError):
        load_config(path)


def test_validation_error_does_not_echo_credentials(tmp_path) -> None:
    path = tmp_path / "config.json"
    document = valid_document()
    document["workers"]["detector-001"]["config"]["confidence"] = 2
    write_document(path, document)

    with pytest.raises(ConfigLoadError) as captured:
        load_config(path)

    assert "secret" not in str(captured.value)
