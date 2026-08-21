"""绕过守护进程、从 PostgreSQL 任务配置启动 Detector。"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from algorithm.common.config import project_root
from algorithm.daemon.configuration import validate_record
from algorithm.database import TaskParameterRepository

from .app import run_detector
from .config import DetectorConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="detector",
        description="Run one configured detector without the daemon.",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv(
            "ALGORITHM_DATABASE_URL",
            "postgresql://sop_vision:sop_vision@localhost:5432/sop_vision",
        ),
    )
    parser.add_argument(
        "--resource-root",
        type=Path,
        default=Path(os.getenv("ALGORITHM_RESOURCE_ROOT", str(project_root()))),
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
    repository = TaskParameterRepository(args.database_url)
    try:
        record = repository.get(args.task_id)
        if record is None:
            raise SystemExit(f"worker {args.task_id!r} is not configured")
        loaded = validate_record(record, args.resource_root)
        if not isinstance(loaded.config, DetectorConfig):
            raise SystemExit(f"worker {args.task_id!r} is not a detector")
        run_detector(loaded.config)
    finally:
        repository.close()


if __name__ == "__main__":
    main()
