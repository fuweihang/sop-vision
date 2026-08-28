import os
import time
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
from algorithm.contracts.detection import (
    DetectionMetrics,
    DetectionObject,
    FrameDetection,
)
from algorithm.daemon.registry import get_worker_definition
from algorithm.demos.viewer import preview_panel as preview_module
from algorithm.demos.viewer import task_panel as task_module
from algorithm.demos.viewer.schema_form import SchemaForm
from algorithm.demos.viewer.task_panel import TaskPanel
from algorithm.demos.viewer.video_feed import RgbFrame
from algorithm.demos.viewer.window import VideoCanvas, ViewerWindow


@pytest.fixture(autouse=True)
def 禁止测试窗口自动访问守护进程(monkeypatch) -> None:
    """窗口结构测试不依赖正在运行的 Daemon。"""

    monkeypatch.setattr(TaskPanel, "refresh_worker_types", lambda _self: None)


def test_窗口包含两个任务页签和两个并排画面() -> None:
    app = QApplication.instance() or QApplication([])
    window = ViewerWindow(task_id="task-1", task_id_2="task-2")
    window.show()
    app.processEvents()

    assert tuple(panel.task_id for panel in window.task_panels) == (
        "task-1",
        "task-2",
    )
    assert window.task_tabs.count() == 2
    assert len(window.preview_panels) == 2
    assert window.size().width() == 1600
    assert window.size().height() == 900
    assert window.main_splitter.orientation() == Qt.Orientation.Horizontal
    assert window.preview_splitter.orientation() == Qt.Orientation.Horizontal
    assert 420 <= window.main_splitter.sizes()[0] <= 460
    assert all(panel.minimumWidth() == 480 for panel in window.preview_panels)
    assert window.task_panel.minimumWidth() == 380
    assert window.advanced_panel.isHidden()
    assert not window.advanced_toggle.isChecked()
    assert not hasattr(window, "rtsp_input")
    assert not hasattr(window, "redis_input")
    assert all(not panel.connect_button.isEnabled() for panel in window.preview_panels)
    window.close()
    app.processEvents()


def test_schema表单可读写detector默认值和嵌套roi() -> None:
    QApplication.instance() or QApplication([])
    schema = get_worker_definition("detector").parameter_schema()
    form = SchemaForm()
    config = _detector_config("camera-1", roi_id="area-1")

    form.set_schema(schema, config)
    payload = form.payload()

    assert payload["confidence"] == 0.5
    assert payload["image_size"] == 640
    assert payload["roi"]["roi_id"] == "area-1"
    assert payload["roi"]["points"][2] == [0.8, 0.8]


def test_两个任务可独立选择worker类型() -> None:
    app = QApplication.instance() or QApplication([])
    window = ViewerWindow(task_id="task-1", task_id_2="task-2")
    first, second = window.task_panels
    for panel in (first, second):
        panel.worker_type_input.blockSignals(True)
        panel.worker_type_input.addItems(["detector", "future-worker"])

    first.worker_type_input.setCurrentText("detector")
    second.worker_type_input.setCurrentText("future-worker")
    first.worker_type_input.blockSignals(False)
    second.worker_type_input.blockSignals(False)

    assert first.worker_type == "detector"
    assert second.worker_type == "future-worker"
    window.close()
    app.processEvents()


def test_视频画布绘制roi多边形边框() -> None:
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


def test_两个任务分别缓存预览地址和roi() -> None:
    app = QApplication.instance() or QApplication([])
    window = ViewerWindow(task_id="task-1", task_id_2="task-2")
    schema = get_worker_definition("detector").parameter_schema()
    first_config = _detector_config("camera-1", roi_id="area-1")
    second_config = _detector_config("camera-2", roi_id="area-2")

    for panel, config in zip(
        window.task_panels,
        (first_config, second_config),
        strict=True,
    ):
        panel.on_operation_finished(
            "load",
            True,
            "",
            {
                "record": SimpleNamespace(
                    worker_type="detector",
                    config=config,
                    updated_at=datetime(2026, 8, 21, tzinfo=UTC),
                ),
                "schema": schema,
            },
        )

    first_preview, second_preview = window.preview_panels
    assert first_preview.preview_rtsp_url == first_config["rtsp_url"]
    assert second_preview.preview_rtsp_url == second_config["rtsp_url"]
    assert first_preview.preview_redis_url == first_config["redis_url"]
    assert second_preview.preview_redis_url == second_config["redis_url"]
    assert first_preview.canvas.roi is not None
    assert first_preview.canvas.roi.roi_id == "area-1"
    assert second_preview.canvas.roi is not None
    assert second_preview.canvas.roi.roi_id == "area-2"

    window.task_panels[0].task_input.setText("task-1-edited")
    assert not first_preview.connect_button.isEnabled()
    assert second_preview.connect_button.isEnabled()
    window.close()
    app.processEvents()


def test_启动成功只自动连接对应画面(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    window = ViewerWindow(task_id="task-1", task_id_2="task-2")
    connected: list[int] = []
    monkeypatch.setattr(
        window.preview_panels[0],
        "connect_sources",
        lambda: connected.append(1),
    )
    monkeypatch.setattr(
        window.preview_panels[1],
        "connect_sources",
        lambda: connected.append(2),
    )

    window.task_panels[1].on_operation_finished(
        "start",
        True,
        "",
        {
            "config": _detector_config("camera-2"),
            "response": {"runtime_state": "running", "pid": 123},
        },
    )

    assert connected == [2]
    assert window.preview_panels[0].preview_task_id is None
    assert window.preview_panels[1].preview_task_id == "task-2"
    window.close()
    app.processEvents()


def test_不含预览字段的worker只禁用对应画面() -> None:
    app = QApplication.instance() or QApplication([])
    window = ViewerWindow(task_id="task-1", task_id_2="task-2")
    first_preview, second_preview = window.preview_panels
    first_preview.set_task_configuration("task-1", {"some_parameter": True})
    second_preview.set_task_configuration("task-2", _detector_config("camera-2"))

    assert not first_preview.connect_button.isEnabled()
    assert first_preview.canvas.roi is None
    assert "不支持视频预览" in first_preview.result_status.text()
    assert second_preview.connect_button.isEnabled()
    window.close()
    app.processEvents()


def test_两路重新连接分别使用自己的缓存配置(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    created: dict[str, list] = {"rtsp": [], "redis": []}

    class FakeFeed:
        def __init__(self, url, **_kwargs):
            created["rtsp"].append(url)

        def start(self):
            pass

        def close(self):
            pass

    class FakeSubscriber:
        def __init__(self, url, task_id, **_kwargs):
            created["redis"].append((url, task_id))

        def start(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(preview_module, "RtspVideoFeed", FakeFeed)
    monkeypatch.setattr(preview_module, "RedisDetectionSubscriber", FakeSubscriber)
    window = ViewerWindow(task_id="task-1", task_id_2="task-2")

    for preview, task_id, camera in (
        (window.preview_panels[0], "task-1", "camera-1"),
        (window.preview_panels[1], "task-2", "camera-2"),
    ):
        preview.set_task_configuration(task_id, _detector_config(camera))
        preview.connect_sources()

    assert created == {
        "rtsp": [
            "rtsp://camera-1/stream",
            "rtsp://camera-2/stream",
        ],
        "redis": [
            ("redis://camera-1/0", "task-1"),
            ("redis://camera-2/0", "task-2"),
        ],
    }
    window.close()
    app.processEvents()


def test_第二路检测结果不会修改第一路状态() -> None:
    app = QApplication.instance() or QApplication([])
    window = ViewerWindow(task_id="task-1", task_id_2="task-2")
    first_preview, second_preview = window.preview_panels
    message = FrameDetection(
        task_id="task-2",
        run_id="run-2",
        frame_id=1,
        frame_ts_ms=1,
        published_at_ms=2,
        source_width=1920,
        source_height=1080,
        objects=(
            DetectionObject(
                class_id=0,
                class_name="person",
                confidence=0.9,
                bbox=(0.1, 0.1, 0.2, 0.3),
            ),
        ),
        metrics=DetectionMetrics(inference_ms=10.0, fps=20.0),
    )

    second_preview._on_detection(second_preview._generation, message)

    assert second_preview.result_status.text() == "检测：1 个目标"
    assert "person 0.90" in second_preview.objects_label.text()
    assert first_preview.result_status.text() == "检测：等待任务配置"
    assert first_preview.objects_label.text() == "目标：-"
    window.close()
    app.processEvents()


def test_相同task_id禁止保存和停止worker() -> None:
    app = QApplication.instance() or QApplication([])
    window = ViewerWindow(task_id="same-task", task_id_2="different-task")
    second = window.task_panels[1]
    second.task_input.setText("same-task")

    second.save_and_command("start")
    assert "两个任务的 Task ID 不能相同" in second.task_status.text()
    assert not second.busy

    second.stop_worker()
    assert "两个任务的 Task ID 不能相同" in second.task_status.text()
    assert not second.busy
    window.close()
    app.processEvents()


def test_第二任务保存时先写数据库再调用对应worker(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    window = ViewerWindow(task_id="task-1", task_id_2="task-2")
    second = window.task_panels[1]
    events: list[tuple] = []
    connected: list[bool] = []

    second.worker_type_input.blockSignals(True)
    second.worker_type_input.addItem("detector")
    second.worker_type_input.setCurrentText("detector")
    second.worker_type_input.blockSignals(False)
    second.schema_form.set_schema(
        get_worker_definition("detector").parameter_schema(),
        _detector_config("camera-2"),
    )

    def fake_save(database_url, task_id, worker_type, config):
        events.append(("save", database_url, task_id, worker_type, config["rtsp_url"]))
        return SimpleNamespace()

    class FakeDaemonClient:
        def __init__(self, daemon_url):
            self.daemon_url = daemon_url

        def command(self, task_id, command):
            events.append(("command", self.daemon_url, task_id, command))
            return {"runtime_state": "running", "pid": 456}

    monkeypatch.setattr(task_module, "save_task", fake_save)
    monkeypatch.setattr(task_module, "DaemonClient", FakeDaemonClient)
    monkeypatch.setattr(
        window.preview_panels[1],
        "connect_sources",
        lambda: connected.append(True),
    )

    second.save_and_command("start")
    assert not second.start_worker_button.isEnabled()
    assert window.task_panels[0].start_worker_button.isEnabled()
    _wait_until(app, lambda: not second.busy)

    assert events == [
        (
            "save",
            window.database_input.text(),
            "task-2",
            "detector",
            "rtsp://camera-2/stream",
        ),
        ("command", window.daemon_input.text(), "task-2", "start"),
    ]
    assert connected == [True]
    window.close()
    app.processEvents()


def test_关闭窗口清理两路预览但不停止worker(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    window = ViewerWindow(task_id="task-1", task_id_2="task-2")
    shutdown: list[int] = []
    stopped: list[int] = []
    for index, preview in enumerate(window.preview_panels, start=1):
        monkeypatch.setattr(
            preview,
            "shutdown",
            lambda index=index: shutdown.append(index),
        )
    for index, panel in enumerate(window.task_panels, start=1):
        monkeypatch.setattr(
            panel,
            "stop_worker",
            lambda index=index: stopped.append(index),
        )

    window.close()
    app.processEvents()

    assert shutdown == [1, 2]
    assert stopped == []


def _detector_config(camera: str, *, roi_id: str = "main") -> dict:
    return {
        "rtsp_url": f"rtsp://{camera}/stream",
        "redis_url": f"redis://{camera}/0",
        "model_path": "resources/models/model.pt",
        "roi": {
            "roi_id": roi_id,
            "points": [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]],
        },
    }


def _wait_until(app: QApplication, predicate, *, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    assert predicate(), "等待 Qt 后台操作完成超时"
