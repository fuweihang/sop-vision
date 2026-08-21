import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from algorithm.daemon.registry import get_worker_definition
from algorithm.demos.viewer.schema_form import SchemaForm
from algorithm.demos.viewer.window import ViewerWindow


def test_window_starts_and_closes_without_connections() -> None:
    app = QApplication.instance() or QApplication([])
    window = ViewerWindow(
        task_id="task-1",
        rtsp_url="rtsp://localhost:8554/cam102",
        redis_url="redis://localhost/0",
    )

    assert window.task_input.text() == "task-1"
    assert not window.disconnect_button.isEnabled()
    window.close()
    app.processEvents()


def test_schema_form_round_trips_detector_defaults_and_nested_roi() -> None:
    QApplication.instance() or QApplication([])
    schema = get_worker_definition("detector").parameter_schema()
    form = SchemaForm()
    config = {
        "camera_id": "camera-1",
        "source_id": "source-1",
        "rtsp_url": "rtsp://camera/stream",
        "redis_url": "redis://localhost/0",
        "model_path": "resources/models/model.pt",
        "roi": {
            "roi_id": "main",
            "points": [[0.1, 0.1], [0.9, 0.1], [0.5, 0.9]],
        },
    }

    form.set_schema(schema, config)
    payload = form.payload()

    assert payload["confidence"] == 0.5
    assert payload["image_size"] == 640
    assert payload["roi"]["points"][2] == [0.5, 0.9]
