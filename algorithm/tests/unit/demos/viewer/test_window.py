import os
from datetime import UTC, datetime
from types import SimpleNamespace

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from algorithm.common.roi import RoiConfig
from algorithm.daemon.registry import get_worker_definition
from algorithm.demos.viewer import window as window_module
from algorithm.demos.viewer.schema_form import SchemaForm
from algorithm.demos.viewer.video_feed import RgbFrame
from algorithm.demos.viewer.window import VideoCanvas, ViewerWindow


def test_window_starts_and_closes_without_connections() -> None:
    app = QApplication.instance() or QApplication([])
    window = ViewerWindow(
        task_id="task-1",
    )
    window.show()
    app.processEvents()

    assert window.task_input.text() == "task-1"
    assert window.size().width() == 1280
    assert window.size().height() == 800
    assert window.main_splitter.orientation() == Qt.Orientation.Horizontal
    assert 400 <= window.main_splitter.sizes()[0] <= 440
    assert window.main_splitter.sizes()[1] > window.main_splitter.sizes()[0]
    assert window.task_panel.minimumWidth() == 360
    assert window.preview_panel.minimumWidth() == 640
    assert window.advanced_panel.isHidden()
    assert not window.advanced_toggle.isChecked()
    assert not hasattr(window, "rtsp_input")
    assert not hasattr(window, "redis_input")
    assert not window.connect_button.isEnabled()
    assert not window.disconnect_button.isEnabled()
    window.close()
    app.processEvents()


def test_schema_form_round_trips_detector_defaults_and_nested_roi() -> None:
    QApplication.instance() or QApplication([])
    schema = get_worker_definition("detector").parameter_schema()
    form = SchemaForm()
    config = {
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


def test_video_canvas_renders_roi_polygon_border() -> None:
    QApplication.instance() or QApplication([])
    canvas = VideoCanvas()
    canvas.resize(640, 360)
    canvas.set_frame(
        RgbFrame(
            sequence=1,
            captured_at_ms=1,
            pixels=np.zeros((360, 640, 3), dtype=np.uint8),
        )
    )
    canvas.set_roi(
        RoiConfig(
            roi_id="main",
            points=((0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)),
        )
    )
    rendered = QImage(640, 360, QImage.Format.Format_ARGB32)
    rendered.fill(Qt.GlobalColor.black)

    canvas.render(rendered)

    yellow_pixels = sum(
        1
        for y in range(rendered.height())
        for x in range(rendered.width())
        if (color := rendered.pixelColor(x, y)).red() > 180
        and color.green() > 140
        and color.blue() < 100
    )
    assert yellow_pixels > 100


def test_loading_task_caches_preview_addresses() -> None:
    app = QApplication.instance() or QApplication([])
    window = ViewerWindow(task_id="task-1")
    config = _detector_config()
    record = SimpleNamespace(
        worker_type="detector",
        config=config,
        updated_at=datetime(2026, 8, 21, tzinfo=UTC),
    )

    window._on_operation_finished(
        "load",
        True,
        "",
        {
            "record": record,
            "schema": get_worker_definition("detector").parameter_schema(),
        },
    )

    assert window._preview_rtsp_url == config["rtsp_url"]
    assert window._preview_redis_url == config["redis_url"]
    assert window.canvas.roi is not None
    assert window.canvas.roi.roi_id == "main"
    assert window.canvas.roi.points[0] == (0.2, 0.2)
    assert window.connect_button.isEnabled()
    window.task_input.setText("another-task")
    assert not window.connect_button.isEnabled()
    window.close()
    app.processEvents()


def test_start_success_updates_preview_config_and_connects(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    window = ViewerWindow(task_id="task-1")
    connected = []
    monkeypatch.setattr(window, "connect_sources", lambda: connected.append(True))

    window._on_operation_finished(
        "start",
        True,
        "",
        {
            "config": _detector_config(),
            "response": {"runtime_state": "running", "pid": 123},
        },
    )

    assert connected == [True]
    window.close()
    app.processEvents()


def test_worker_without_preview_fields_disables_preview() -> None:
    app = QApplication.instance() or QApplication([])
    window = ViewerWindow(task_id="task-1")
    window._set_preview_config(_detector_config())
    window._set_preview_config({"some_parameter": True})

    assert not window.connect_button.isEnabled()
    assert window.canvas.roi is None
    assert "不支持视频预览" in window.result_status.text()
    window.close()
    app.processEvents()


def test_reconnect_uses_cached_task_configuration(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    created = {}

    class FakeFeed:
        def __init__(self, url, **_kwargs):
            created["rtsp_url"] = url

        def start(self):
            created["feed_started"] = True

        def close(self):
            pass

    class FakeSubscriber:
        def __init__(self, url, task_id, **_kwargs):
            created["redis_url"] = url
            created["task_id"] = task_id

        def start(self):
            created["subscriber_started"] = True

        def close(self):
            pass

    monkeypatch.setattr(window_module, "RtspVideoFeed", FakeFeed)
    monkeypatch.setattr(window_module, "RedisDetectionSubscriber", FakeSubscriber)
    window = ViewerWindow(task_id="task-1")
    window._set_preview_config(_detector_config())

    window.connect_sources()

    assert created == {
        "rtsp_url": "rtsp://camera/stream",
        "redis_url": "redis://localhost/0",
        "task_id": "task-1",
        "feed_started": True,
        "subscriber_started": True,
    }
    window.close()
    app.processEvents()


def _detector_config() -> dict:
    return {
        "rtsp_url": "rtsp://camera/stream",
        "redis_url": "redis://localhost/0",
        "model_path": "resources/models/model.pt",
        "roi": {
            "roi_id": "main",
            "points": [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]],
        },
    }
