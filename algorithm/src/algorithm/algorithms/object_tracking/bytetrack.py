"""基于 Ultralytics YOLO 和 ByteTrack 的多目标追踪适配器。"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from algorithm.algorithms.yolo import (
    DetectionBatch,
    YoloRuntime,
    detections_from_result,
)


class YoloTracker(YoloRuntime):
    """使用 YOLO 检测结果和 ByteTrack 为连续视频帧分配轨迹编号。

    每个实例只服务一个 Worker 和一路固定 RTSP 地址。RTSP 地址变化时应用端
    会重启 Worker，因此新的实例会自然获得全新的 ByteTrack 状态。
    """

    def __init__(
        self,
        model_path: Path,
        *,
        image_size: int = 640,
        confidence: float = 0.25,
        device: str | None = None,
    ) -> None:
        super().__init__(
            model_path,
            image_size=image_size,
            confidence=confidence,
            device=device,
        )
        # Ultralytics 延迟导入追踪模块；在 Worker 报告就绪前主动导入，确保 lap
        # 缺失时由 Daemon 收到启动失败，而不是在首帧到达后才崩溃。
        from ultralytics.trackers import register_tracker as _register_tracker  # noqa: F401

    def track(self, frame: np.ndarray) -> DetectionBatch:
        """追踪一帧图像，并在连续调用之间保留 ByteTrack 状态。"""

        result = self._model.track(
            **self._prediction_arguments(frame),
            persist=True,
            tracker="bytetrack.yaml",
        )[0]
        return detections_from_result(result)
