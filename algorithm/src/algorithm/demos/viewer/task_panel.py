"""单个 Worker 任务的 Schema 表单、数据库读写和控制按钮。"""

from __future__ import annotations

import threading
from collections.abc import Callable

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .schema_form import SchemaForm, SchemaValidationError
from .task_client import DaemonClient, load_task, save_task


class TaskPanel(QWidget):
    """独立编辑和控制一个任务，耗时操作统一放到后台线程。"""

    task_id_changed = Signal(str)
    preview_configuration_changed = Signal(str, object, bool)
    _operation_finished = Signal(str, bool, str, object)

    def __init__(
        self,
        *,
        slot_number: int,
        task_id: str,
        daemon_url: Callable[[], str],
        database_url: Callable[[], str],
        validate_unique_task_id: Callable[[TaskPanel], str | None],
    ) -> None:
        super().__init__()
        self._slot_number = slot_number
        self._daemon_url = daemon_url
        self._database_url = database_url
        self._validate_unique_task_id = validate_unique_task_id
        self._busy = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        identity = QFormLayout()
        task_row = QHBoxLayout()
        self.task_input = QLineEdit(task_id)
        self.load_task_button = QPushButton("加载")
        task_row.addWidget(self.task_input, stretch=1)
        task_row.addWidget(self.load_task_button)
        identity.addRow("Task ID", task_row)

        worker_row = QHBoxLayout()
        self.worker_type_input = QComboBox()
        self.refresh_types_button = QPushButton("刷新")
        worker_row.addWidget(self.worker_type_input, stretch=1)
        worker_row.addWidget(self.refresh_types_button)
        identity.addRow("Worker 类型", worker_row)
        layout.addLayout(identity)

        self.schema_form = SchemaForm()
        schema_scroll = QScrollArea()
        schema_scroll.setWidgetResizable(True)
        schema_scroll.setWidget(self.schema_form)
        layout.addWidget(schema_scroll, stretch=1)

        controls = QHBoxLayout()
        self.start_worker_button = QPushButton("保存并启动")
        self.reload_worker_button = QPushButton("保存并重载")
        self.stop_worker_button = QPushButton("停止 Worker")
        controls.addWidget(self.start_worker_button)
        controls.addWidget(self.reload_worker_button)
        controls.addWidget(self.stop_worker_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.task_status = QLabel("任务配置：等待加载 Schema")
        self.task_status.setWordWrap(True)
        layout.addWidget(self.task_status)

        self._busy_controls = (
            self.task_input,
            self.load_task_button,
            self.worker_type_input,
            self.refresh_types_button,
            self.schema_form,
            self.start_worker_button,
            self.reload_worker_button,
            self.stop_worker_button,
        )
        self.task_input.textChanged.connect(self._task_id_edited)
        self.refresh_types_button.clicked.connect(self.refresh_worker_types)
        self.load_task_button.clicked.connect(self.load_task_configuration)
        self.worker_type_input.currentTextChanged.connect(self.load_worker_schema)
        self.start_worker_button.clicked.connect(lambda: self.save_and_command("start"))
        self.reload_worker_button.clicked.connect(
            lambda: self.save_and_command("reload")
        )
        self.stop_worker_button.clicked.connect(self.stop_worker)
        self._operation_finished.connect(self.on_operation_finished)
        QTimer.singleShot(0, self.refresh_worker_types)

    @property
    def task_id(self) -> str:
        return self.task_input.text().strip()

    @property
    def worker_type(self) -> str:
        return self.worker_type_input.currentText().strip()

    @property
    def busy(self) -> bool:
        return self._busy

    def refresh_worker_types(self) -> None:
        if self._busy:
            return
        daemon_url = self._daemon_url().strip()
        self.task_status.setText("任务配置：正在获取 Worker 类型…")
        self._run_operation(
            "types",
            lambda: {"types": DaemonClient(daemon_url).worker_types()},
        )

    def load_worker_schema(self, worker_type: str) -> None:
        if self._busy or not worker_type:
            return
        daemon_url = self._daemon_url().strip()
        self.task_status.setText(f"任务配置：正在加载 {worker_type} Schema…")
        self._run_operation(
            "schema",
            lambda: {
                "worker_type": worker_type,
                "schema": DaemonClient(daemon_url).schema(worker_type),
            },
        )

    def load_task_configuration(self) -> None:
        if self._busy:
            return
        task_id = self.task_id
        if not task_id:
            self.task_status.setText("任务配置：Task ID 不能为空")
            return
        database_url = self._database_url().strip()
        daemon_url = self._daemon_url().strip()
        self.task_status.setText("任务配置：正在读取数据库…")

        def operation() -> dict[str, object]:
            record = load_task(database_url, task_id)
            if record is None:
                raise RuntimeError(f"任务 {task_id!r} 尚未配置")
            return {
                "record": record,
                "schema": DaemonClient(daemon_url).schema(record.worker_type),
            }

        self._run_operation("load", operation)

    def save_and_command(self, command: str) -> None:
        if self._busy:
            return
        task_id = self.task_id
        worker_type = self.worker_type
        if not task_id:
            self.task_status.setText("任务配置：Task ID 不能为空")
            return
        duplicate_error = self._validate_unique_task_id(self)
        if duplicate_error is not None:
            self.task_status.setText(f"任务配置：{duplicate_error}")
            return
        if not worker_type:
            self.task_status.setText("任务配置：Worker 类型不能为空")
            return
        try:
            config = self.schema_form.payload()
        except SchemaValidationError as error:
            self.task_status.setText(f"任务配置校验失败：{error}")
            return
        database_url = self._database_url().strip()
        daemon_url = self._daemon_url().strip()
        self.task_status.setText("任务配置：正在提交数据库并调用守护进程…")

        def operation() -> dict[str, object]:
            # 数据库提交成功后才能启动 Worker，保证 Daemon 读到的就是刚保存的配置。
            record = save_task(database_url, task_id, worker_type, config)
            response = DaemonClient(daemon_url).command(task_id, command)
            return {"record": record, "response": response, "config": config}

        self._run_operation(command, operation)

    def stop_worker(self) -> None:
        if self._busy:
            return
        task_id = self.task_id
        if not task_id:
            self.task_status.setText("任务配置：Task ID 不能为空")
            return
        duplicate_error = self._validate_unique_task_id(self)
        if duplicate_error is not None:
            self.task_status.setText(f"任务配置：{duplicate_error}")
            return
        daemon_url = self._daemon_url().strip()
        self.task_status.setText("任务配置：正在停止 Worker…")
        self._run_operation(
            "stop",
            lambda: {"response": DaemonClient(daemon_url).command(task_id, "stop")},
        )

    def _run_operation(self, name: str, callback: Callable[[], object]) -> None:
        """运行一个任务操作；忙碌期间拒绝同一任务的第二个操作。"""

        self._set_busy(True)

        def run() -> None:
            try:
                result = callback()
            except Exception as error:  # noqa: BLE001 - 后台任务统一转成界面错误
                self._operation_finished.emit(name, False, str(error), None)
            else:
                self._operation_finished.emit(name, True, "", result)

        threading.Thread(
            target=run,
            name=f"viewer-task-{self._slot_number}-{name}",
            daemon=True,
        ).start()

    def on_operation_finished(
        self,
        name: str,
        succeeded: bool,
        detail: str,
        value: object,
    ) -> None:
        """在 Qt 主线程中应用后台操作结果并恢复当前任务按钮。"""

        self._set_busy(False)
        if not succeeded or not isinstance(value, dict):
            self.task_status.setText(f"任务配置失败：{detail}")
            return
        if name == "types":
            current = self.worker_type
            self.worker_type_input.blockSignals(True)
            self.worker_type_input.clear()
            self.worker_type_input.addItems(list(value["types"]))
            index = self.worker_type_input.findText(current or "detector")
            if index >= 0:
                self.worker_type_input.setCurrentIndex(index)
            self.worker_type_input.blockSignals(False)
            self.task_status.setText("任务配置：Worker 类型已更新")
            if self.worker_type:
                self.load_worker_schema(self.worker_type)
        elif name == "schema":
            if value["worker_type"] != self.worker_type:
                return
            self.schema_form.set_schema(value["schema"])
            self.task_status.setText("任务配置：Schema 已加载")
        elif name == "load":
            record = value["record"]
            self.worker_type_input.blockSignals(True)
            if self.worker_type_input.findText(record.worker_type) < 0:
                self.worker_type_input.addItem(record.worker_type)
            self.worker_type_input.setCurrentText(record.worker_type)
            self.worker_type_input.blockSignals(False)
            self.schema_form.set_schema(value["schema"], record.config)
            self.preview_configuration_changed.emit(self.task_id, record.config, False)
            self.task_status.setText(
                f"任务配置：已加载，最后更新 {record.updated_at.isoformat()}"
            )
        elif name in {"start", "reload"}:
            config = value["config"]
            response = value["response"]
            self.task_status.setText(
                f"任务配置：{response['runtime_state']}，PID {response['pid']}"
            )
            self.preview_configuration_changed.emit(self.task_id, config, True)
        elif name == "stop":
            self.task_status.setText("任务配置：Worker 已停止")

    def _task_id_edited(self, task_id: str) -> None:
        self.task_id_changed.emit(task_id.strip())

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for control in self._busy_controls:
            control.setEnabled(not busy)
