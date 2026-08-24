"""请求 trace ID 的异步上下文与日志适配。"""

import logging
from contextvars import ContextVar, Token

# ContextVar 随 asyncio task 传播但彼此隔离，比进程全局变量更适合并发请求；默认 None 使
# 启动任务、迁移脚本等非 HTTP 上下文也能安全读取。
_trace_id_context: ContextVar[str | None] = ContextVar("trace_id", default=None)


def bind_trace_id(trace_id: str) -> Token[str | None]:
    """把入口生成的 trace ID 绑定到当前异步执行上下文。

    该函数只供 HTTP 入口使用。业务层与日志层应调用 :func:`get_trace_id` 读取同一个值，
    不能自行生成新的关联 ID。
    """

    return _trace_id_context.set(trace_id)


def reset_trace_id(token: Token[str | None]) -> None:
    """请求结束后恢复父上下文，避免连接复用或后台任务串用其他请求的 ID。"""

    _trace_id_context.reset(token)


def get_trace_id() -> str | None:
    """返回当前请求 trace ID；非请求上下文返回 ``None``。"""

    return _trace_id_context.get()


class TraceIdLogFilter(logging.Filter):
    """为日志记录补充当前请求的 ``trace_id`` 字段。

    Filter 只读取 ContextVar，不接受调用方传入另一个 trace ID，因此应用日志、响应头和
    Problem body 可以保持同源。未处于请求上下文时使用 ``-``，便于 formatter 稳定输出。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """把当前上下文 trace ID 写入日志记录，并始终允许该记录继续输出。

        即使调用者尝试通过 ``extra`` 提供另一个 trace_id，这里也会用请求 ContextVar 覆盖，
        从机制上避免同一请求产生多个不一致的关联 ID。
        """

        record.trace_id = get_trace_id() or "-"
        return True
