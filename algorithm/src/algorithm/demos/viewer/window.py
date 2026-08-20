"""单任务、非同步检测结果叠加 Viewer。"""

from __future__ import annotations

import sys
import threading
import time

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCloseEvent, QFontMetrics, QImage, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from algorithm.contracts.detection import DetectionObject, FrameDetection

from .geometry import fit_content_rect, map_normalized_bbox
from .redis_subscriber import RedisDetectionSubscriber, RedisSubscriberStatus
from .state import DetectionOverlayState
from .video_feed import RtspVideoFeed, RgbFrame


class ViewerSignals(QObject):
    detection = Signal(int, object)
    redis_status = Signal(int, bool, str)
    redis_reset = Signal(int)
    rtsp_status = Signal(int, bool, str)


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

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#111827"))
        if self._image is None:
            painter.setPen(QColor("#9ca3af"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "等待 RTSP 视频")
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

    def __init__(self, *, task_id: str, rtsp_url: str, redis_url: str) -> None:
        super().__init__()
        self.setWindowTitle("SOP Vision Detection Viewer")
        self.resize(1100, 760)
        self._signals = ViewerSignals()
        self._signals.detection.connect(self._on_detection)
        self._signals.redis_status.connect(self._on_redis_status)
        self._signals.redis_reset.connect(self._on_redis_reset)
        self._signals.rtsp_status.connect(self._on_rtsp_status)
        self._generation = 0
        self._video_feed: RtspVideoFeed | None = None
        self._subscriber: RedisDetectionSubscriber | None = None
        self._last_frame_sequence = 0
        self._overlay = DetectionOverlayState(expires_after_seconds=2.0)

        central = QWidget()
        layout = QVBoxLayout(central)
        form = QFormLayout()
        self.task_input = QLineEdit(task_id)
        self.rtsp_input = QLineEdit(rtsp_url)
        self.redis_input = QLineEdit(redis_url)
        form.addRow("Task ID", self.task_input)
        form.addRow("RTSP URL", self.rtsp_input)
        form.addRow("Redis URL", self.redis_input)
        layout.addLayout(form)

        controls = QHBoxLayout()
        self.connect_button = QPushButton("连接")
        self.disconnect_button = QPushButton("断开")
        self.disconnect_button.setEnabled(False)
        controls.addWidget(self.connect_button)
        controls.addWidget(self.disconnect_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        warning = QLabel("当前为非同步最新结果叠加模式：检测框不保证对应当前显示帧")
        warning.setStyleSheet("color: #d97706; font-weight: 600;")
        layout.addWidget(warning)

        self.canvas = VideoCanvas()
        layout.addWidget(self.canvas, stretch=1)

        statuses = QHBoxLayout()
        self.rtsp_status = QLabel("RTSP：未连接")
        self.redis_status = QLabel("Redis：未连接")
        self.result_status = QLabel("检测：等待连接")
        statuses.addWidget(self.rtsp_status)
        statuses.addWidget(self.redis_status)
        statuses.addWidget(self.result_status)
        statuses.addStretch(1)
        layout.addLayout(statuses)

        self.objects_label = QLabel("目标：-")
        self.metrics_label = QLabel("推理：-    Worker FPS：-    消息年龄：-")
        layout.addWidget(self.objects_label)
        layout.addWidget(self.metrics_label)
        self.setCentralWidget(central)

        self.connect_button.clicked.connect(self.connect_sources)
        self.disconnect_button.clicked.connect(self.disconnect_sources)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()

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

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
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

    def _on_redis_status(
        self, generation: int, connected: bool, detail: str
    ) -> None:
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

    def _on_rtsp_status(
        self, generation: int, connected: bool, detail: str
    ) -> None:
        if generation == self._generation:
            state = "已连接" if connected else detail
            self.rtsp_status.setText(f"RTSP：{state}")


def _unix_ms() -> int:
    return time.time_ns() // 1_000_000


def run_viewer(*, task_id: str, rtsp_url: str, redis_url: str) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = ViewerWindow(task_id=task_id, rtsp_url=rtsp_url, redis_url=redis_url)
    window.show()
    return app.exec()
