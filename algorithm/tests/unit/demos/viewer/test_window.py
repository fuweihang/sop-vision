import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

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
