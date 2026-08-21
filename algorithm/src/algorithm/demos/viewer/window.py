"""单任务、非同步检测结果叠加 Viewer。"""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from algorithm.contracts.detection import DetectionObject, FrameDetection

from .geometry import fit_content_rect, map_normalized_bbox
from .redis_subscriber import RedisDetectionSubscriber
from .schema_form import SchemaForm, SchemaValidationError
from .state import DetectionOverlayState
from .task_client import DaemonClient, load_task, save_task
from .video_feed import RgbFrame, RtspVideoFeed

DEFAULT_DATABASE_URL = "postgresql://sop_vision:sop_vision@localhost:5432/sop_vision"


class ViewerSignals(QObject):
    detection = Signal(int, object)
    redis_status = Signal(int, bool, str)
    redis_reset = Signal(int)
    rtsp_status = Signal(int, bool, str)
    operation_finished = Signal(str, bool, str, object)


class VideoCanvas(QWidget):
    """等比显示视频，并在真实内容区域内绘制归一化 bbox。"""

    def __init__(self) -> None:
        super().__init__()
        self._image: QImage | None = None
        self._objects: tuple[DetectionObject, ...] = ()
        self.setMinimumSize(640, 360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_frame(self, frame: RgbFrame) -> None:
        pixels = frame.pixels
        height, width = pixels.shape[:2]
        image = QImage(
            pixels.data,
            width,
            height,
            int(pixels.strides[0]),
            QImage.Format.Format_RGB888,
        )
        self._image = image.copy()
        self.update()

    def clear_frame(self) -> None:
        self._image = None
        self.update()

    def set_objects(self, objects: tuple[DetectionObject, ...]) -> None:
        self._objects = objects
        self.update()

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#111827"))
        if self._image is None:
            painter.setPen(QColor("#9ca3af"))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, "等待 RTSP 视频"
            )
            return

        content = fit_content_rect(
            self.width(),
            self.height(),
            self._image.width(),
            self._image.height(),
        )
        target = QRectF(content.x, content.y, content.width, content.height)
        painter.drawImage(target, self._image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        for detection in self._objects:
            left, top, right, bottom = map_normalized_bbox(detection.bbox, content)
            color = _class_color(detection.class_id)
            painter.setPen(QPen(color, 2.0))
            painter.drawRect(QRectF(left, top, right - left, bottom - top))
            label = f"{detection.class_name} {detection.confidence:.2f}"
            metrics = QFontMetrics(painter.font())
            label_width = metrics.horizontalAdvance(label) + 8
            label_height = metrics.height() + 4
            label_top = max(content.y, top - label_height)
            label_rect = QRectF(left, label_top, label_width, label_height)
            painter.fillRect(label_rect, color)
            painter.setPen(QColor("white"))
            painter.drawText(
                label_rect.adjusted(4, 0, -4, 0),
                Qt.AlignmentFlag.AlignVCenter,
                label,
            )


def _class_color(class_id: int) -> QColor:
    colors = ("#22c55e", "#3b82f6", "#f59e0b", "#ef4444", "#a855f7")
    return QColor(colors[class_id % len(colors)])


class ViewerWindow(QMainWindow):
    """管理一条 RTSP 连接和一个任务的 Redis 检测订阅。"""

    def __init__(
        self,
        *,
        task_id: str,
        rtsp_url: str,
        redis_url: str,
        daemon_url: str = "http://127.0.0.1:8090",
        database_url: str = DEFAULT_DATABASE_URL,
    ) -> None:
        super().__init__()
        self.setWindowTitle("SOP Vision Detection Viewer")
        self.resize(1100, 760)
        self._signals = ViewerSignals()
        self._signals.detection.connect(self._on_detection)
        self._signals.redis_status.connect(self._on_redis_status)
        self._signals.redis_reset.connect(self._on_redis_reset)
        self._signals.rtsp_status.connect(self._on_rtsp_status)
        self._signals.operation_finished.connect(self._on_operation_finished)
        self._generation = 0
        self._video_feed: RtspVideoFeed | None = None
        self._subscriber: RedisDetectionSubscriber | None = None
        self._last_frame_sequence = 0
        self._overlay = DetectionOverlayState(expires_after_seconds=2.0)

        central = QWidget()
        layout = QVBoxLayout(central)

        task_group = QGroupBox("Worker 任务配置（外部客户端模拟）")
        task_layout = QVBoxLayout(task_group)
        endpoints = QFormLayout()
        self.daemon_input = QLineEdit(daemon_url)
        self.database_input = QLineEdit(database_url)
        endpoints.addRow("Daemon URL", self.daemon_input)
        endpoints.addRow("Database URL", self.database_input)
        task_layout.addLayout(endpoints)

        identity = QHBoxLayout()
        self.task_input = QLineEdit(task_id)
        self.worker_type_input = QComboBox()
        self.worker_type_input.setMinimumWidth(160)
        self.refresh_types_button = QPushButton("刷新类型")
        self.load_task_button = QPushButton("加载任务")
        identity.addWidget(QLabel("Task ID"))
        identity.addWidget(self.task_input, stretch=1)
        identity.addWidget(QLabel("Worker 类型"))
        identity.addWidget(self.worker_type_input)
        identity.addWidget(self.refresh_types_button)
        identity.addWidget(self.load_task_button)
        task_layout.addLayout(identity)

        self.schema_form = SchemaForm()
        schema_scroll = QScrollArea()
        schema_scroll.setWidgetResizable(True)
        schema_scroll.setMaximumHeight(260)
        schema_scroll.setWidget(self.schema_form)
        task_layout.addWidget(schema_scroll)

        task_controls = QHBoxLayout()
        self.start_worker_button = QPushButton("保存并启动")
        self.reload_worker_button = QPushButton("保存并重载")
        self.stop_worker_button = QPushButton("停止 Worker")
        task_controls.addWidget(self.start_worker_button)
        task_controls.addWidget(self.reload_worker_button)
        task_controls.addWidget(self.stop_worker_button)
        task_controls.addStretch(1)
        task_layout.addLayout(task_controls)
        self.task_status = QLabel("任务配置：等待加载 Schema")
        task_layout.addWidget(self.task_status)
        layout.addWidget(task_group)

        source_group = QGroupBox("Detector 预览")
        source_layout = QVBoxLayout(source_group)
        form = QFormLayout()
        self.rtsp_input = QLineEdit(rtsp_url)
        self.redis_input = QLineEdit(redis_url)
        form.addRow("RTSP URL", self.rtsp_input)
        form.addRow("Redis URL", self.redis_input)
        source_layout.addLayout(form)

        controls = QHBoxLayout()
        self.connect_button = QPushButton("连接")
        self.disconnect_button = QPushButton("断开")
        self.disconnect_button.setEnabled(False)
        controls.addWidget(self.connect_button)
        controls.addWidget(self.disconnect_button)
        controls.addStretch(1)
        source_layout.addLayout(controls)

        warning = QLabel("当前为非同步最新结果叠加模式：检测框不保证对应当前显示帧")
        warning.setStyleSheet("color: #d97706; font-weight: 600;")
        source_layout.addWidget(warning)

        self.canvas = VideoCanvas()
        source_layout.addWidget(self.canvas, stretch=1)

        statuses = QHBoxLayout()
        self.rtsp_status = QLabel("RTSP：未连接")
        self.redis_status = QLabel("Redis：未连接")
        self.result_status = QLabel("检测：等待连接")
        statuses.addWidget(self.rtsp_status)
        statuses.addWidget(self.redis_status)
        statuses.addWidget(self.result_status)
        statuses.addStretch(1)
        source_layout.addLayout(statuses)

        self.objects_label = QLabel("目标：-")
        self.metrics_label = QLabel("推理：-    Worker FPS：-    消息年龄：-")
        source_layout.addWidget(self.objects_label)
        source_layout.addWidget(self.metrics_label)
        layout.addWidget(source_group, stretch=1)
        self.setCentralWidget(central)

        self.connect_button.clicked.connect(self.connect_sources)
        self.disconnect_button.clicked.connect(self.disconnect_sources)
        self.refresh_types_button.clicked.connect(self.refresh_worker_types)
        self.load_task_button.clicked.connect(self.load_task_configuration)
        self.worker_type_input.currentTextChanged.connect(self.load_worker_schema)
        self.start_worker_button.clicked.connect(lambda: self.save_and_command("start"))
        self.reload_worker_button.clicked.connect(
            lambda: self.save_and_command("reload")
        )
        self.stop_worker_button.clicked.connect(self.stop_worker)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        QTimer.singleShot(0, self.refresh_worker_types)

    def refresh_worker_types(self) -> None:
        daemon_url = self.daemon_input.text().strip()
        self.task_status.setText("任务配置：正在获取 Worker 类型…")
        self._run_operation(
            "types",
            lambda: {"types": DaemonClient(daemon_url).worker_types()},
        )

    def load_worker_schema(self, worker_type: str) -> None:
        if not worker_type:
            return
        daemon_url = self.daemon_input.text().strip()
        self.task_status.setText(f"任务配置：正在加载 {worker_type} Schema…")
        self._run_operation(
            "schema",
            lambda: {
                "worker_type": worker_type,
                "schema": DaemonClient(daemon_url).schema(worker_type),
            },
        )

    def load_task_configuration(self) -> None:
        task_id = self.task_input.text().strip()
        if not task_id:
            self.task_status.setText("任务配置：Task ID 不能为空")
            return
        database_url = self.database_input.text().strip()
        daemon_url = self.daemon_input.text().strip()
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
        task_id = self.task_input.text().strip()
        worker_type = self.worker_type_input.currentText().strip()
        if not task_id or not worker_type:
            self.task_status.setText("任务配置：Task ID 和 Worker 类型不能为空")
            return
        try:
            config = self.schema_form.payload()
        except SchemaValidationError as error:
            self.task_status.setText(f"任务配置校验失败：{error}")
            return
        database_url = self.database_input.text().strip()
        daemon_url = self.daemon_input.text().strip()
        self.task_status.setText("任务配置：正在提交数据库并调用守护进程…")

        def operation() -> dict[str, object]:
            record = save_task(database_url, task_id, worker_type, config)
            response = DaemonClient(daemon_url).command(task_id, command)
            return {"record": record, "response": response, "config": config}

        self._run_operation(command, operation)

    def stop_worker(self) -> None:
        task_id = self.task_input.text().strip()
        if not task_id:
            self.task_status.setText("任务配置：Task ID 不能为空")
            return
        daemon_url = self.daemon_input.text().strip()
        self.task_status.setText("任务配置：正在停止 Worker…")
        self._run_operation(
            "stop",
            lambda: {"response": DaemonClient(daemon_url).command(task_id, "stop")},
        )

    def _run_operation(self, name: str, callback: Callable[[], object]) -> None:
        def run() -> None:
            try:
                result = callback()
            except Exception as error:  # noqa: BLE001 - background UI boundary
                self._signals.operation_finished.emit(name, False, str(error), None)
            else:
                self._signals.operation_finished.emit(name, True, "", result)

        threading.Thread(
            target=run,
            name=f"viewer-{name}",
            daemon=True,
        ).start()

    def _on_operation_finished(
        self,
        name: str,
        succeeded: bool,
        detail: str,
        value: object,
    ) -> None:
        if not succeeded or not isinstance(value, dict):
            self.task_status.setText(f"任务配置失败：{detail}")
            return
        if name == "types":
            current = self.worker_type_input.currentText()
            self.worker_type_input.blockSignals(True)
            self.worker_type_input.clear()
            self.worker_type_input.addItems(list(value["types"]))
            index = self.worker_type_input.findText(current or "detector")
            if index >= 0:
                self.worker_type_input.setCurrentIndex(index)
            self.worker_type_input.blockSignals(False)
            self.task_status.setText("任务配置：Worker 类型已更新")
            if self.worker_type_input.currentText():
                self.load_worker_schema(self.worker_type_input.currentText())
        elif name == "schema":
            if value["worker_type"] != self.worker_type_input.currentText():
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
            self.task_status.setText(
                f"任务配置：已加载，最后更新 {record.updated_at.isoformat()}"
            )
        elif name in {"start", "reload"}:
            config = value["config"]
            response = value["response"]
            self.task_status.setText(
                f"任务配置：{response['runtime_state']}，PID {response['pid']}"
            )
            rtsp_url = config.get("rtsp_url")
            redis_url = config.get("redis_url")
            if isinstance(rtsp_url, str) and isinstance(redis_url, str):
                self.rtsp_input.setText(rtsp_url)
                self.redis_input.setText(redis_url)
                self.connect_sources()
        elif name == "stop":
            self.task_status.setText("任务配置：Worker 已停止")

    def connect_sources(self) -> None:
        task_id = self.task_input.text().strip()
        rtsp_url = self.rtsp_input.text().strip()
        redis_url = self.redis_input.text().strip()
        if not task_id or not rtsp_url or not redis_url:
            self.result_status.setText("检测：Task、RTSP 和 Redis 均不能为空")
            return

        self._stop_components()
        generation = self._generation
        self._overlay.clear()
        self._last_frame_sequence = 0
        self.canvas.set_objects(())
        self.canvas.clear_frame()

        self._video_feed = RtspVideoFeed(
            rtsp_url,
            on_status=lambda status: self._signals.rtsp_status.emit(
                generation, status.connected, status.detail
            ),
        )
        self._subscriber = RedisDetectionSubscriber(
            redis_url,
            task_id,
            on_message=lambda message: self._signals.detection.emit(
                generation, message
            ),
            on_status=lambda status: self._signals.redis_status.emit(
                generation, status.connected, status.detail
            ),
            on_reset=lambda: self._signals.redis_reset.emit(generation),
        )
        self._video_feed.start()
        self._subscriber.start()
        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(True)
        self.result_status.setText("检测：等待结果")

    def disconnect_sources(self) -> None:
        self._stop_components()
        self.canvas.set_objects(())
        self.canvas.clear_frame()
        self._overlay.clear()
        self.rtsp_status.setText("RTSP：未连接")
        self.redis_status.setText("Redis：未连接")
        self.result_status.setText("检测：已断开")
        self.objects_label.setText("目标：-")
        self.metrics_label.setText("推理：-    Worker FPS：-    消息年龄：-")
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._timer.stop()
        self._stop_components()
        event.accept()

    def _stop_components(self) -> None:
        self._generation += 1
        video_feed = self._video_feed
        subscriber = self._subscriber
        self._video_feed = None
        self._subscriber = None
        if video_feed is None and subscriber is None:
            return

        def close_in_background() -> None:
            if subscriber is not None:
                subscriber.close()
            if video_feed is not None:
                video_feed.close()

        threading.Thread(
            target=close_in_background,
            name="viewer-connection-cleanup",
            daemon=True,
        ).start()

    def _refresh(self) -> None:
        if self._video_feed is not None:
            frame = self._video_feed.get_latest(self._last_frame_sequence)
            if frame is not None:
                self._last_frame_sequence = frame.sequence
                self.canvas.set_frame(frame)

        if self._overlay.expire_if_needed():
            self.canvas.set_objects(())
            self.result_status.setText("检测：结果已过期")
            self.objects_label.setText("目标：-")

        message = self._overlay.message
        if message is not None:
            age_ms = max(0, _unix_ms() - message.published_at_ms)
            self.metrics_label.setText(
                f"推理：{message.metrics.inference_ms:.1f} ms    "
                f"Worker FPS：{message.metrics.fps:.1f}    "
                f"消息年龄：{age_ms} ms"
            )

    def _on_detection(self, generation: int, value: object) -> None:
        if generation != self._generation or not isinstance(value, FrameDetection):
            return
        run_changed = self._overlay.update(value)
        if run_changed:
            self.canvas.set_objects(())
        self.canvas.set_objects(value.objects)
        if value.objects:
            self.result_status.setText(f"检测：{len(value.objects)} 个目标")
            summary = ", ".join(
                f"{item.class_name} {item.confidence:.2f}" for item in value.objects
            )
            self.objects_label.setText(f"目标：{summary}")
        else:
            self.result_status.setText("检测：无目标")
            self.objects_label.setText("目标：无")

    def _on_redis_status(self, generation: int, connected: bool, detail: str) -> None:
        if generation == self._generation:
            state = "已连接" if connected else detail
            self.redis_status.setText(f"Redis：{state}")

    def _on_redis_reset(self, generation: int) -> None:
        if generation != self._generation:
            return
        self._overlay.clear()
        self.canvas.set_objects(())
        self.result_status.setText("检测：Redis 断线，等待重连")
        self.objects_label.setText("目标：-")

    def _on_rtsp_status(self, generation: int, connected: bool, detail: str) -> None:
        if generation == self._generation:
            state = "已连接" if connected else detail
            self.rtsp_status.setText(f"RTSP：{state}")


def _unix_ms() -> int:
    return time.time_ns() // 1_000_000


def run_viewer(
    *,
    task_id: str,
    rtsp_url: str,
    redis_url: str,
    daemon_url: str = "http://127.0.0.1:8090",
    database_url: str = DEFAULT_DATABASE_URL,
) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setFont(QFont("Source Han Sans CN", 10))
    window = ViewerWindow(
        task_id=task_id,
        rtsp_url=rtsp_url,
        redis_url=redis_url,
        daemon_url=daemon_url,
        database_url=database_url,
    )
    window.show()
    return app.exec()
