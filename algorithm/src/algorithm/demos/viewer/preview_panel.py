"""单路摄像头预览组件，管理独立的 RTSP、Redis 和检测绘制状态。"""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetrics, QImage, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from algorithm.common.roi import RoiConfig
from algorithm.contracts.detection import DetectionObject, FrameDetection

from .geometry import (
    ContentRect,
    fit_content_rect,
    map_normalized_bbox,
    map_normalized_polygon,
)
from .redis_subscriber import RedisDetectionSubscriber
from .state import DetectionOverlayState
from .video_feed import RgbFrame, RtspVideoFeed


class _PreviewSignals(QObject):
    """把拉流和订阅线程的回调安全地转发到 Qt 主线程。"""

    detection = Signal(int, object)
    redis_status = Signal(int, bool, str)
    redis_reset = Signal(int)
    rtsp_status = Signal(int, bool, str)


class VideoCanvas(QWidget):
    """等比显示视频，并在视频内容区域内绘制 ROI 和检测框。"""

    def __init__(self) -> None:
        super().__init__()
        self._image: QImage | None = None
        self._objects: tuple[DetectionObject, ...] = ()
        self._roi: RoiConfig | None = None
        # 双画面需要在常见的 1600px 宽屏幕中并排显示，因此这里不能继续使用
        # 单画面时期的 640px 最小宽度。480x270 仍保持 16:9 且能看清检测框。
        self.setMinimumSize(480, 270)
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
        # RtspVideoFeed 会继续复用底层 numpy 内存，必须复制后再交给 Qt 绘制。
        self._image = image.copy()
        self.update()

    def clear_frame(self) -> None:
        self._image = None
        self.update()

    def set_objects(self, objects: tuple[DetectionObject, ...]) -> None:
        self._objects = objects
        self.update()

    @property
    def roi(self) -> RoiConfig | None:
        return self._roi

    def set_roi(self, roi: RoiConfig | None) -> None:
        self._roi = roi
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
        self._draw_roi(painter, content)

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

    def _draw_roi(self, painter: QPainter, content: ContentRect) -> None:
        roi = self._roi
        if roi is None:
            return
        mapped = map_normalized_polygon(roi.points, content)
        polygon = QPolygonF([QPointF(x, y) for x, y in mapped])
        color = QColor("#facc15")
        pen = QPen(color, 2.5, Qt.PenStyle.DashLine)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(polygon)

        first_x, first_y = mapped[0]
        label = f"ROI: {roi.roi_id}"
        metrics = QFontMetrics(painter.font())
        label_width = metrics.horizontalAdvance(label) + 8
        label_height = metrics.height() + 4
        label_x = max(
            content.x,
            min(first_x, content.x + content.width - label_width),
        )
        label_y = max(content.y, first_y - label_height)
        label_rect = QRectF(label_x, label_y, label_width, label_height)
        painter.fillRect(label_rect, QColor(250, 204, 21, 210))
        painter.setPen(QColor("#111827"))
        painter.drawText(
            label_rect.adjusted(4, 0, -4, 0),
            Qt.AlignmentFlag.AlignVCenter,
            label,
        )


class PreviewPanel(QGroupBox):
    """显示一个任务的视频，并独立管理该任务的两个后台连接。"""

    def __init__(self, slot_label: str, task_id: str) -> None:
        super().__init__()
        self._slot_label = slot_label
        self._task_id = task_id.strip()
        self._signals = _PreviewSignals()
        self._signals.detection.connect(self._on_detection)
        self._signals.redis_status.connect(self._on_redis_status)
        self._signals.redis_reset.connect(self._on_redis_reset)
        self._signals.rtsp_status.connect(self._on_rtsp_status)

        # 每一路都有自己的 generation。旧连接即使晚到一条回调，也不能更新新连接
        # 或另一路画面。
        self._generation = 0
        self._video_feed: RtspVideoFeed | None = None
        self._subscriber: RedisDetectionSubscriber | None = None
        self._preview_task_id: str | None = None
        self._preview_rtsp_url: str | None = None
        self._preview_redis_url: str | None = None
        self._last_frame_sequence = 0
        self._overlay = DetectionOverlayState(expires_after_seconds=2.0)

        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)

        controls = QHBoxLayout()
        self.connect_button = QPushButton("重新连接")
        self.connect_button.setEnabled(False)
        self.disconnect_button = QPushButton("断开")
        self.disconnect_button.setEnabled(False)
        controls.addWidget(self.connect_button)
        controls.addWidget(self.disconnect_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        warning = QLabel("非同步最新结果叠加：检测框不保证对应当前显示帧")
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #d97706; font-weight: 600;")
        layout.addWidget(warning)

        self.canvas = VideoCanvas()
        layout.addWidget(self.canvas, stretch=1)

        statuses = QHBoxLayout()
        self.rtsp_status = QLabel("RTSP：未连接")
        self.redis_status = QLabel("Redis：未连接")
        self.result_status = QLabel("检测：等待任务配置")
        statuses.addWidget(self.rtsp_status)
        statuses.addWidget(self.redis_status)
        statuses.addWidget(self.result_status)
        statuses.addStretch(1)
        layout.addLayout(statuses)

        self.objects_label = QLabel("目标：-")
        self.objects_label.setWordWrap(True)
        self.metrics_label = QLabel("推理：-    Worker FPS：-    消息年龄：-")
        layout.addWidget(self.objects_label)
        layout.addWidget(self.metrics_label)

        self.connect_button.clicked.connect(self.connect_sources)
        self.disconnect_button.clicked.connect(self.disconnect_sources)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._update_title()

    @property
    def preview_task_id(self) -> str | None:
        return self._preview_task_id

    @property
    def preview_rtsp_url(self) -> str | None:
        return self._preview_rtsp_url

    @property
    def preview_redis_url(self) -> str | None:
        return self._preview_redis_url

    def set_task_id(self, task_id: str) -> None:
        """响应配置页 Task ID 修改，只断开当前预览，不影响另一任务。"""

        self._task_id = task_id.strip()
        self._update_title()
        if self._preview_task_id is None:
            return
        if self._task_id == self._preview_task_id:
            self.connect_button.setEnabled(
                self._video_feed is None and self._subscriber is None
            )
            if self.connect_button.isEnabled():
                self.result_status.setText("检测：任务配置已就绪")
            return
        if self._video_feed is not None or self._subscriber is not None:
            self.disconnect_sources()
        self.connect_button.setEnabled(False)
        self.result_status.setText("检测：请先加载当前任务配置")

    def set_task_configuration(
        self,
        task_id: str,
        config: object,
        auto_connect: bool = False,
    ) -> None:
        """缓存任务配置；只有启动或重载成功时才自动连接预览。"""

        if self._video_feed is not None or self._subscriber is not None:
            self.disconnect_sources()
        self._task_id = task_id.strip()
        self._update_title()

        roi = None
        if isinstance(config, dict) and config.get("roi") is not None:
            try:
                roi = RoiConfig.model_validate(config["roi"])
            except ValueError:
                # 数据库中的旧数据可能绕过当前 Schema。ROI 无效时仍允许查看视频，
                # 只是不能绘制错误的多边形。
                roi = None
        self.canvas.set_roi(roi)

        rtsp_url = config.get("rtsp_url") if isinstance(config, dict) else None
        redis_url = config.get("redis_url") if isinstance(config, dict) else None
        if (
            isinstance(rtsp_url, str)
            and rtsp_url.strip()
            and isinstance(redis_url, str)
            and redis_url.strip()
        ):
            self._preview_rtsp_url = rtsp_url.strip()
            self._preview_redis_url = redis_url.strip()
            self._preview_task_id = self._task_id
            self.connect_button.setEnabled(True)
            self.result_status.setText("检测：任务配置已就绪")
            if auto_connect:
                self.connect_sources()
            return

        self._preview_task_id = None
        self._preview_rtsp_url = None
        self._preview_redis_url = None
        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(False)
        self.canvas.clear_frame()
        self.canvas.set_objects(())
        self.result_status.setText("检测：当前 Worker 不支持视频预览")

    def has_preview_config(self) -> bool:
        return (
            self._preview_task_id == self._task_id
            and bool(self._preview_task_id)
            and self._preview_rtsp_url is not None
            and self._preview_redis_url is not None
        )

    def connect_sources(self) -> None:
        """使用当前任务缓存的地址建立独立 RTSP 和 Redis 连接。"""

        if not self._task_id or not self.has_preview_config():
            self.result_status.setText("检测：当前任务不支持视频预览")
            self.connect_button.setEnabled(False)
            return
        assert self._preview_rtsp_url is not None
        assert self._preview_redis_url is not None

        self._stop_components()
        generation = self._generation
        self._overlay.clear()
        self._last_frame_sequence = 0
        self.canvas.set_objects(())
        self.canvas.clear_frame()

        self._video_feed = RtspVideoFeed(
            self._preview_rtsp_url,
            on_status=lambda status: self._signals.rtsp_status.emit(
                generation, status.connected, status.detail
            ),
        )
        self._subscriber = RedisDetectionSubscriber(
            self._preview_redis_url,
            self._task_id,
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
        """断开当前画面的预览连接，但不调用 Daemon 停止 Worker。"""

        self._stop_components()
        self.canvas.set_objects(())
        self.canvas.clear_frame()
        self._overlay.clear()
        self.rtsp_status.setText("RTSP：未连接")
        self.redis_status.setText("Redis：未连接")
        self.result_status.setText("检测：已断开")
        self.objects_label.setText("目标：-")
        self.metrics_label.setText("推理：-    Worker FPS：-    消息年龄：-")
        self.connect_button.setEnabled(self.has_preview_config())
        self.disconnect_button.setEnabled(False)

    def shutdown(self) -> None:
        """窗口关闭时停止刷新并清理连接，不改变 Worker 运行状态。"""

        self._timer.stop()
        self._stop_components()

    def _update_title(self) -> None:
        task = self._task_id or "未设置 Task ID"
        self.setTitle(f"{self._slot_label} · {task}")

    def _stop_components(self) -> None:
        self._generation += 1
        video_feed = self._video_feed
        subscriber = self._subscriber
        self._video_feed = None
        self._subscriber = None
        if video_feed is None and subscriber is None:
            return

        # close() 可能等待网络线程退出，不能在 Qt 主线程中同步执行。
        def close_in_background() -> None:
            if subscriber is not None:
                subscriber.close()
            if video_feed is not None:
                video_feed.close()

        threading.Thread(
            target=close_in_background,
            name=f"viewer-{self._slot_label}-connection-cleanup",
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


def _class_color(class_id: int) -> QColor:
    colors = ("#22c55e", "#3b82f6", "#f59e0b", "#ef4444", "#a855f7")
    return QColor(colors[class_id % len(colors)])


def _unix_ms() -> int:
    return time.time_ns() // 1_000_000
