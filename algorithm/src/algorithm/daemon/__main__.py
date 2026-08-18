"""``algorithm-daemon`` 命令行入口。"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

import uvicorn

from .api import create_app
from .manager import WorkerManager


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="algorithm-daemon",
        description="Run the local-config SOP Vision AIWorker daemon.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(os.getenv("ALGORITHM_CONFIG_PATH", "config.json")),
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
        args.config,
        startup_timeout=args.startup_timeout,
        graceful_stop_timeout=args.stop_timeout,
    )
    uvicorn.run(create_app(manager=manager), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
