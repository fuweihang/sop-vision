"""双任务 Qt Viewer 窗口。"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QFont
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QMainWindow,
    QSplitter,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .preview_panel import PreviewPanel
from .preview_panel import VideoCanvas as _VideoCanvas
from .task_panel import TaskPanel

DEFAULT_DATABASE_URL = "postgresql://sop_vision:sop_vision@localhost:5432/sop_vision"
# VideoCanvas 原先从 window 模块导入。保留这个名称，现有调试代码无需同时修改。
VideoCanvas = _VideoCanvas


class CollapsibleSection(QWidget):
    """默认收起不常修改的连接配置，给任务表单留出更多空间。"""

    def __init__(self, title: str, content: QWidget) -> None:
        super().__init__()
        self.toggle = QToolButton()
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(False)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.content = content
        self.content.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.toggle)
        layout.addWidget(self.content)
        self.toggle.toggled.connect(self._set_expanded)

    def _set_expanded(self, expanded: bool) -> None:
        self.toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self.content.setVisible(expanded)


class ViewerWindow(QMainWindow):
    """管理两个独立任务，并同时显示两路摄像头画面。"""

    def __init__(
        self,
        *,
        task_id: str,
        task_id_2: str = "detector-002",
        daemon_url: str = "http://127.0.0.1:8090",
        database_url: str = DEFAULT_DATABASE_URL,
    ) -> None:
        super().__init__()
        self.setWindowTitle("SOP Vision 双任务检测 Viewer")
        self.resize(1600, 900)

        task_group = QGroupBox("Worker 任务配置（外部客户端模拟）")
        task_group.setMinimumWidth(380)
        task_group.setMaximumWidth(560)
        task_layout = QVBoxLayout(task_group)

        # Daemon 和数据库属于 Viewer 的公共连接。RTSP 和 Redis 仍位于各任务
        # 的 Schema 表单中，因此两路视频地址可以独立保存和加载。
        advanced_content = QWidget()
        endpoints = QFormLayout()
        endpoints.setContentsMargins(0, 0, 0, 0)
        self.daemon_input = QLineEdit(daemon_url)
        self.database_input = QLineEdit(database_url)
        endpoints.addRow("Daemon URL", self.daemon_input)
        endpoints.addRow("Database URL", self.database_input)
        advanced_content.setLayout(endpoints)
        self.advanced_section = CollapsibleSection("高级连接设置", advanced_content)
        self.advanced_toggle = self.advanced_section.toggle
        self.advanced_panel = self.advanced_section.content
        task_layout.addWidget(self.advanced_section)

        self.task_tabs = QTabWidget()
        task_layout.addWidget(self.task_tabs, stretch=1)

        panels: list[TaskPanel] = []
        for slot_number, initial_task_id in enumerate((task_id, task_id_2), start=1):
            panel = TaskPanel(
                slot_number=slot_number,
                task_id=initial_task_id,
                daemon_url=lambda: self.daemon_input.text(),
                database_url=lambda: self.database_input.text(),
                validate_unique_task_id=self._validate_unique_task_id,
            )
            panels.append(panel)
            self.task_tabs.addTab(panel, f"任务 {slot_number}")
        self.task_panels = tuple(panels)

        self.preview_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.preview_splitter.setChildrenCollapsible(False)
        previews: list[PreviewPanel] = []
        for slot_number, panel in enumerate(self.task_panels, start=1):
            preview = PreviewPanel(f"摄像头 {slot_number}", panel.task_id)
            panel.task_id_changed.connect(preview.set_task_id)
            panel.preview_configuration_changed.connect(preview.set_task_configuration)
            previews.append(preview)
            self.preview_splitter.addWidget(preview)
            self.preview_splitter.setStretchFactor(slot_number - 1, 1)
        self.preview_panels = tuple(previews)
        self.preview_splitter.setSizes([580, 580])

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.addWidget(task_group)
        self.main_splitter.addWidget(self.preview_splitter)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([440, 1160])
        self.task_panel = task_group
        self.preview_panel = self.preview_splitter
        self.setCentralWidget(self.main_splitter)

        # 保留第一路常用控件的旧属性名，避免已有调试脚本因双路改造立即失效。
        # 新代码应优先使用 task_panels 和 preview_panels 明确选择任务。
        first_task = self.task_panels[0]
        first_preview = self.preview_panels[0]
        self.task_input = first_task.task_input
        self.worker_type_input = first_task.worker_type_input
        self.refresh_types_button = first_task.refresh_types_button
        self.load_task_button = first_task.load_task_button
        self.schema_form = first_task.schema_form
        self.start_worker_button = first_task.start_worker_button
        self.reload_worker_button = first_task.reload_worker_button
        self.stop_worker_button = first_task.stop_worker_button
        self.task_status = first_task.task_status
        self.connect_button = first_preview.connect_button
        self.disconnect_button = first_preview.disconnect_button
        self.canvas = first_preview.canvas
        self.rtsp_status = first_preview.rtsp_status
        self.redis_status = first_preview.redis_status
        self.result_status = first_preview.result_status
        self.objects_label = first_preview.objects_label
        self.metrics_label = first_preview.metrics_label

    def _validate_unique_task_id(self, current: TaskPanel) -> str | None:
        """保存或控制前检查两路 Task ID，避免同时操作同一个 Worker。"""

        task_id = current.task_id
        if not task_id:
            return None
        for panel in self.task_panels:
            if panel is not current and panel.task_id == task_id:
                return "两个任务的 Task ID 不能相同"
        return None

    # 以下方法继续转发到第一路，兼容原有的单任务调试调用。
    def refresh_worker_types(self) -> None:
        self.task_panels[0].refresh_worker_types()

    def load_worker_schema(self, worker_type: str) -> None:
        self.task_panels[0].load_worker_schema(worker_type)

    def load_task_configuration(self) -> None:
        self.task_panels[0].load_task_configuration()

    def save_and_command(self, command: str) -> None:
        self.task_panels[0].save_and_command(command)

    def stop_worker(self) -> None:
        self.task_panels[0].stop_worker()

    def connect_sources(self) -> None:
        self.preview_panels[0].connect_sources()

    def disconnect_sources(self) -> None:
        self.preview_panels[0].disconnect_sources()

    def _set_preview_config(self, config: object) -> None:
        self.preview_panels[0].set_task_configuration(
            self.task_panels[0].task_id,
            config,
        )

    def _has_preview_config(self) -> bool:
        return self.preview_panels[0].has_preview_config()

    def _on_operation_finished(
        self,
        name: str,
        succeeded: bool,
        detail: str,
        value: object,
    ) -> None:
        self.task_panels[0].on_operation_finished(name, succeeded, detail, value)

    @property
    def _preview_task_id(self) -> str | None:
        return self.preview_panels[0].preview_task_id

    @property
    def _preview_rtsp_url(self) -> str | None:
        return self.preview_panels[0].preview_rtsp_url

    @property
    def _preview_redis_url(self) -> str | None:
        return self.preview_panels[0].preview_redis_url

    def closeEvent(self, event: QCloseEvent) -> None:
        for preview in self.preview_panels:
            preview.shutdown()
        event.accept()


def run_viewer(
    *,
    task_id: str,
    task_id_2: str = "detector-002",
    daemon_url: str = "http://127.0.0.1:8090",
    database_url: str = DEFAULT_DATABASE_URL,
) -> int:
    """启动固定包含两个任务槽位的 Qt Viewer。"""

    app = QApplication.instance() or QApplication(sys.argv)
    app.setFont(QFont("Source Han Sans CN", 10))
    window = ViewerWindow(
        task_id=task_id,
        task_id_2=task_id_2,
        daemon_url=daemon_url,
        database_url=database_url,
    )
    window.show()
    return app.exec()
