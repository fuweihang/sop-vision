"""``algorithm-viewer`` 命令行入口。"""

from __future__ import annotations

import argparse
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="algorithm-viewer",
        description="Display one RTSP stream with the latest Redis detection result.",
    )
    parser.add_argument("--task-id", default="detector-001")
    parser.add_argument("--rtsp-url", default="rtsp://localhost:8554/cam102")
    parser.add_argument("--redis-url", default="redis://127.0.0.1:63793/0")
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
        rtsp_url=args.rtsp_url,
        redis_url=args.redis_url,
    )


if __name__ == "__main__":
    raise SystemExit(main())
