"""``algorithm-daemon`` 命令行入口。"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

import uvicorn

from algorithm.common.config import project_root
from algorithm.database import TaskParameterRepository

from .api import create_app
from .manager import WorkerManager

DEFAULT_DATABASE_URL = "postgresql://sop_vision:sop_vision@localhost:5432/sop_vision"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="algorithm-daemon",
        description="Run the PostgreSQL-backed SOP Vision AIWorker daemon.",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("ALGORITHM_DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    parser.add_argument(
        "--resource-root",
        type=Path,
        default=Path(os.getenv("ALGORITHM_RESOURCE_ROOT", str(project_root()))),
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=int(os.getenv("ALGORITHM_MAX_WORKERS", "4")),
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--startup-timeout", type=float, default=60.0)
    parser.add_argument("--stop-timeout", type=float, default=10.0)
    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(processName)s %(name)s: %(message)s",
    )
    args = build_parser().parse_args()
    manager = WorkerManager(
        TaskParameterRepository(args.database_url),
        args.resource_root,
        max_workers=args.max_workers,
        startup_timeout=args.startup_timeout,
        graceful_stop_timeout=args.stop_timeout,
    )
    uvicorn.run(create_app(manager=manager), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
