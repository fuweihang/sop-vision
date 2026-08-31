"""Detector Worker 的严格参数模型。"""

from __future__ import annotations

from algorithm.workers.config import VideoWorkerConfig


class DetectorConfig(VideoWorkerConfig):
    """Detector 的独立配置类型，字段来自视频 Worker 公共配置。"""
