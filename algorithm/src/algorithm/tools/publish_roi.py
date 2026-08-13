"""校验并通过 Redis 发布一条 ROI 更新。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import redis
from pydantic import ValidationError

from algorithm.common.config import (
    DEFAULT_REDIS_URL,
    DEFAULT_ROI_CHANNEL,
    DEFAULT_TASK_ID,
)
from algorithm.common.roi import RoiUpdate


def build_parser() -> argparse.ArgumentParser:
    """构建 ``publish-roi`` 命令的参数解析器。"""

    parser = argparse.ArgumentParser(
        prog="publish-roi",
        description="Publish a validated detector ROI update through Redis Pub/Sub.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--json", dest="json_payload", help="inline ROI JSON")
    source.add_argument("--file", type=Path, help="path to an ROI JSON file")
    parser.add_argument("--redis-url", default=DEFAULT_REDIS_URL)
    parser.add_argument("--task-id", default=DEFAULT_TASK_ID)
    parser.add_argument(
        "--channel",
        default=None,
        help=f"Redis channel; default is {DEFAULT_ROI_CHANNEL}",
    )
    return parser


def main() -> int:
    """解析参数、校验并发布 ROI 更新；返回进程退出码。"""

    args = build_parser().parse_args()
    try:
        payload = (
            args.json_payload
            if args.json_payload is not None
            else args.file.read_text(encoding="utf-8")
        )
        update = RoiUpdate.model_validate_json(payload)
        if update.task_id != args.task_id:
            raise ValueError(
                f"message task_id {update.task_id!r} does not match --task-id {args.task_id!r}"
            )
    except (OSError, ValidationError, ValueError) as error:
        print(f"Invalid ROI update: {error}", file=sys.stderr)
        return 2

    channel = args.channel or f"vision:config:roi:{args.task_id}"
    client: redis.Redis | None = None
    try:
        client = redis.Redis.from_url(
            args.redis_url,
            decode_responses=True,
            socket_connect_timeout=3.0,
            socket_timeout=3.0,
        )
        subscribers = client.publish(channel, update.model_dump_json())
    except redis.RedisError as error:
        print(f"Redis publish failed: {error}", file=sys.stderr)
        return 1
    finally:
        if client is not None:
            client.close()

    action = "updated" if update.enabled else "cleared"
    print(
        f"ROI {action} on {channel}; active subscribers: {subscribers}"
    )
    if subscribers == 0:
        print(
            "Warning: Pub/Sub is not persistent; no running detector received this update.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
