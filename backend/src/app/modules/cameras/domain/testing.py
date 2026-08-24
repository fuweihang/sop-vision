"""后续 Cameras 切片可复用的确定性领域测试替身。"""

from collections.abc import Iterable
from datetime import datetime
from uuid import RFC_4122, UUID


class FixedIdGenerator:
    """按预置顺序返回 UUID v4，耗尽时快速失败而非生成随机值。"""

    def __init__(self, values: Iterable[UUID]) -> None:
        self._values = tuple(values)
        if any(value.version != 4 or value.variant != RFC_4122 for value in self._values):
            raise ValueError("固定 ID 生成器只接受 UUID v4")
        self._index = 0

    def new_id(self) -> UUID:
        if self._index >= len(self._values):
            raise RuntimeError("固定 ID 生成器的预置值已经耗尽")
        value = self._values[self._index]
        self._index += 1
        return value


class FixedClock:
    """返回固定时间，并允许测试显式推进到另一个时刻。"""

    def __init__(self, current: datetime) -> None:
        self.current = current

    def now(self) -> datetime:
        return self.current

    def set(self, current: datetime) -> None:
        """显式设置下一次读取值，避免测试依赖真实时间流逝。"""

        self.current = current
