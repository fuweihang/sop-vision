"""Cameras 领域创建与时间推进所需的最小端口。"""

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4


class IdGenerator(Protocol):
    """生成服务端业务 UUID；测试可注入确定序列。"""

    def new_id(self) -> UUID:
        """返回一个新的 UUID v4。"""
        ...


class Clock(Protocol):
    """提供可替换的 UTC 当前时间。"""

    def now(self) -> datetime:
        """返回带时区的当前时间。"""
        ...


class Uuid4Generator:
    """生产环境使用的 RFC 9562 UUID v4 生成器。"""

    def new_id(self) -> UUID:
        return uuid4()


class SystemClock:
    """生产环境使用的 UTC 系统时钟。"""

    def now(self) -> datetime:
        return datetime.now(UTC)
