"""``algorithm-viewer`` 命令行入口。"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="algorithm-viewer",
        description="配置两个数据库任务，并同时显示两路最新检测结果。",
    )
    parser.add_argument("--task-id", default="detector-001")
    parser.add_argument("--task-id-2", default="detector-002")
    parser.add_argument("--daemon-url", default="http://127.0.0.1:8090")
    parser.add_argument(
        "--database-url",
        default=os.getenv(
            "ALGORITHM_DATABASE_URL",
            "postgresql://sop_vision:sop_vision@localhost:5432/sop_vision",
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        from .window import run_viewer
    except ModuleNotFoundError as error:
        if error.name == "PySide6":
            raise SystemExit(
                "PySide6 is not installed; run `uv sync --extra viewer` first."
            ) from error
        raise
    return run_viewer(
        task_id=args.task_id,
        task_id_2=args.task_id_2,
        daemon_url=args.daemon_url,
        database_url=args.database_url,
    )


if __name__ == "__main__":
    raise SystemExit(main())
