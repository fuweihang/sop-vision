"""Tracker Worker 的严格参数模型。"""

from __future__ import annotations

from algorithm.workers.config import VideoWorkerConfig


class TrackerConfig(VideoWorkerConfig):
    """Tracker 的独立配置类型，并固定使用 Ultralytics 内置 ByteTrack 配置。

    v1 不开放 ByteTrack 阈值或 YAML 路径，避免数据库任务配置依赖未受控制的
    本地文件。后续需要调参时可在此模型中增加经过范围校验的明确字段。
    """
