"""绕过守护进程、从本地配置启动单个 Detector 的调试入口。"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from algorithm.daemon.config_loader import load_config

from .app import run_detector
from .config import DetectorConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="detector",
        description="Run one configured detector without the daemon.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(os.getenv("ALGORITHM_CONFIG_PATH", "config.json")),
    )
    parser.add_argument("--task-id", required=True)
    return parser


def main() -> None:
    """组合命令行参数与默认配置并启动 detector。"""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = build_parser().parse_args()
    loaded = load_config(args.config).workers.get(args.task_id)
    if loaded is None:
        raise SystemExit(f"worker {args.task_id!r} is not in {args.config}")
    if not isinstance(loaded.config, DetectorConfig):
        raise SystemExit(f"worker {args.task_id!r} is not a detector")
    config = loaded.config
    run_detector(config)


if __name__ == "__main__":
    main()
