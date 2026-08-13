"""Detector Worker 的命令行入口。"""

from __future__ import annotations

import argparse
import logging
from dataclasses import replace
from pathlib import Path

from algorithm.common.config import DetectorConfig

from .app import run_detector


def build_parser(defaults: DetectorConfig | None = None) -> argparse.ArgumentParser:
    """构建 ``detector`` 命令的参数解析器，默认值取自环境配置。"""

    defaults = defaults or DetectorConfig.from_environment()
    parser = argparse.ArgumentParser(
        prog="detector",
        description="Run the SOP Vision YOLO26n RTSP detector demo.",
    )
    parser.add_argument("--rtsp-url", default=defaults.rtsp_url)
    parser.add_argument("--redis-url", default=defaults.redis_url)
    parser.add_argument("--task-id", default=defaults.task_id)
    parser.add_argument(
        "--roi-channel",
        default=None,
        help="Redis Pub/Sub channel; defaults to vision:config:roi:{task_id}",
    )
    parser.add_argument("--model", type=Path, default=defaults.model_path)
    parser.add_argument("--image-size", type=int, default=defaults.image_size)
    parser.add_argument("--confidence", type=float, default=defaults.confidence)
    parser.add_argument(
        "--device",
        default=defaults.device,
        help="Ultralytics device such as 0, cuda:0, cpu, or auto; default is GPU 0",
    )
    parser.add_argument(
        "--reconnect-delay",
        type=float,
        default=defaults.reconnect_delay_seconds,
    )
    return parser


def main() -> None:
    """组合命令行参数与默认配置并启动 detector。"""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    defaults = DetectorConfig.from_environment()
    args = build_parser(defaults).parse_args()
    if args.roi_channel is not None:
        roi_channel = args.roi_channel
    elif args.task_id == defaults.task_id:
        roi_channel = defaults.roi_channel
    else:
        roi_channel = f"vision:config:roi:{args.task_id}"

    config = replace(
        defaults,
        rtsp_url=args.rtsp_url,
        redis_url=args.redis_url,
        task_id=args.task_id,
        roi_channel=roi_channel,
        model_path=args.model,
        image_size=args.image_size,
        confidence=args.confidence,
        device=(
            None
            if args.device is None or args.device.lower() == "auto"
            else args.device
        ),
        reconnect_delay_seconds=args.reconnect_delay,
    )
    run_detector(config)


if __name__ == "__main__":
    main()
