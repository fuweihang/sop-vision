"""绕过守护进程、从 PostgreSQL 任务配置启动 Tracker。"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from algorithm.common.config import (
    AlgorithmConfigError,
    default_config_path,
    load_algorithm_config,
)
from algorithm.daemon.configuration import validate_record
from algorithm.database import TaskParameterRepository

from .app import run_tracker
from .config import TrackerConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tracker",
        description="不经过 Daemon，运行一个已配置的 ByteTrack Worker。",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv(
            "ALGORITHM_DATABASE_URL",
            "postgresql://sop_vision:sop_vision@localhost:5432/sop_vision",
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(),
        help="外围 TOML 路径，默认读取 ALGORITHM_CONFIG 或 algorithm/config.toml。",
    )
    parser.add_argument("--task-id", required=True)
    return parser


def main() -> None:
    """读取已提交的 Tracker 配置并启动单个调试进程。"""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = build_parser().parse_args()
    try:
        outer_config = load_algorithm_config(args.config)
    except AlgorithmConfigError as error:
        raise SystemExit(str(error)) from error
    repository = TaskParameterRepository(args.database_url)
    try:
        record = repository.get(args.task_id)
        if record is None:
            raise SystemExit(f"Worker {args.task_id!r} 尚未配置")
        loaded = validate_record(record, outer_config)
        if not isinstance(loaded.config, TrackerConfig):
            raise SystemExit(f"Worker {args.task_id!r} 不是 tracker 类型")
        run_tracker(loaded.config)
    finally:
        repository.close()


if __name__ == "__main__":
    main()
