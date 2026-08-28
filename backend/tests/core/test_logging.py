"""统一日志 Formatter、字段安全边界和重复初始化测试。"""

import json
import logging
import os
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import pytest

from app.core.http.trace import TraceIdLogFilter
from app.core.logging import (
    BackendStreamHandler,
    ConsoleFormatter,
    JsonFormatter,
    configure_logging,
    safe_exception_fields,
)


def make_record(
    *,
    name: str = "app.modules.cameras.application.create",
    level: int = logging.WARNING,
    message: str = "Camera 已保存，但媒体操作未全部成功",
    **extra: object,
) -> logging.LogRecord:
    """构造时间固定的 LogRecord，避免时区和运行速度影响断言。"""

    record = logging.LogRecord(name, level, __file__, 17, message, (), None)
    record.created = datetime(2026, 8, 28, 8, 49, 8, 431000, tzinfo=UTC).timestamp()
    for key, value in extra.items():
        setattr(record, key, value)
    return record


@pytest.fixture
def set_process_timezone() -> Iterator[Callable[[str], None]]:
    """临时修改进程 ``TZ``，并在用例结束后恢复 C 运行库的时区缓存。"""

    original_timezone = os.environ.get("TZ")

    def apply(timezone_name: str) -> None:
        os.environ["TZ"] = timezone_name
        # 测试进程启动后才修改环境变量，必须通知 C 运行库重新读取 TZ；生产容器在 Python
        # 启动前已经注入变量，不需要应用代码主动调用 tzset。
        time.tzset()

    try:
        yield apply
    finally:
        if original_timezone is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original_timezone
        time.tzset()


def test_console_formatter_uses_local_columns_event_order_and_visible_controls(
    set_process_timezone: Callable[[str], None],
) -> None:
    """console 使用容器地区时间，固定列和控制字符转义保持不变。"""

    set_process_timezone("Asia/Shanghai")

    record = make_record(
        message="Camera 已保存\n但媒体操作\t未全部成功",
        event="camera.media_sync_degraded",
        operation="post_commit_media_sync",
        outcome="degraded",
        camera_id="camera-1",
        failed_count=0,
        trace_id="tr_abc123",
    )

    rendered = ConsoleFormatter().format(record)

    assert rendered == (
        "2026-08-28 16:49:08 WARN  camera.create         "
        "Camera 已保存\\n但媒体操作\\t未全部成功  "
        "operation=post_commit_media_sync result=degraded camera=camera-1 failed=0 "
        "trace=tr_abc123"
    )
    assert len(rendered.splitlines()) == 1


def test_console_and_json_formatters_follow_the_same_container_timezone(
    set_process_timezone: Callable[[str], None],
) -> None:
    """两种输出必须读取同一个 ``TZ``，且不显示毫秒、偏移或时区缩写。"""

    set_process_timezone("Asia/Shanghai")
    record = make_record()

    console_timestamp = ConsoleFormatter().format(record).split(" WARN", maxsplit=1)[0]
    json_timestamp = json.loads(JsonFormatter().format(record))["timestamp"]

    assert console_timestamp == "2026-08-28 16:49:08"
    assert json_timestamp == console_timestamp
    assert all(marker not in console_timestamp for marker in (".431", "Z", "+08:00", "CST"))


def test_formatter_uses_utc_when_container_timezone_is_utc(
    set_process_timezone: Callable[[str], None],
) -> None:
    """部署把 ``TZ`` 改为 UTC 后，无需修改应用配置即可得到对应地区时间。"""

    set_process_timezone("UTC")

    payload = json.loads(JsonFormatter().format(make_record()))

    assert payload["timestamp"] == "2026-08-28 08:49:08"


def test_json_formatter_keeps_types_order_zero_and_ignores_unknown_fields() -> None:
    """JSON 只输出白名单字段，数值不转字符串，有意义的 0 必须保留。"""

    sentinel = "never-render-this-secret"
    record = make_record(
        name="app.modules.cameras.application.reconciliation",
        message="媒体对账完成",
        level=logging.INFO,
        event="media_reconciliation.round_completed",
        outcome="success",
        desired_count=4,
        managed_path_count=4,
        ensured_count=0,
        released_count=1,
        duration_ms=12,
        trace_id=None,
        # 这两个字段虽是公共白名单，但不属于 round_completed，仍必须按事件表排除。
        error_type="ShouldBeIgnoredForThisEvent",
        error_frames=["secret.py:call:1"],
        password=sentinel,
        empty_value="-",
    )

    rendered = JsonFormatter().format(record)
    payload = json.loads(rendered)

    assert list(payload) == [
        "timestamp",
        "level",
        "logger",
        "component",
        "message",
        "event",
        "outcome",
        "desired_count",
        "managed_path_count",
        "ensured_count",
        "released_count",
        "duration_ms",
    ]
    assert payload["ensured_count"] == 0
    assert isinstance(payload["duration_ms"], int)
    assert sentinel not in rendered
    assert "trace_id" not in payload


@pytest.mark.parametrize(
    ("logger_name", "component"),
    [
        ("root", "backend"),
        ("app.factory", "backend.lifecycle"),
        ("app.modules.cameras.application.create.child", "camera.create"),
        ("uvicorn.access", "server.access"),
        ("uvicorn.error", "server"),
        ("app.custom.worker", "custom.worker"),
        ("third_party", "third_party"),
    ],
)
def test_formatter_maps_component_by_longest_logger_prefix(
    logger_name: str,
    component: str,
) -> None:
    """固定映射优先于通用 app 前缀，未映射 Logger 使用稳定回退。"""

    payload = json.loads(JsonFormatter().format(make_record(name=logger_name)))

    assert payload["component"] == component


def test_safe_exception_fields_never_include_exception_text_or_absolute_path() -> None:
    """未知异常只留下类型和代码位置，不保留异常对象、消息或绝对路径。"""

    sentinel = "database-password-must-not-leak"

    def raise_unknown_error() -> None:
        raise RuntimeError(sentinel)

    try:
        raise_unknown_error()
    except RuntimeError as error:
        fields = safe_exception_fields(error)
    else:  # pragma: no cover - 防止测试辅助函数被误改为不再抛错。
        pytest.fail("测试异常未抛出")

    assert fields["error_type"] == "RuntimeError"
    assert fields["error_frames"][-1].startswith("test_logging.py:raise_unknown_error:")
    assert sentinel not in repr(fields)
    assert "/home/" not in repr(fields)
    assert all(isinstance(value, str) for value in fields["error_frames"])


def test_formatter_converts_third_party_exc_info_without_rendering_exception_text() -> None:
    """第三方 exc_info 也只能输出安全类型和帧，不能走标准 Formatter 的 traceback 文本。"""

    sentinel = "third-party-secret"
    try:
        raise ValueError(sentinel)
    except ValueError:
        record = logging.LogRecord(
            "uvicorn.error",
            logging.ERROR,
            __file__,
            1,
            "服务器处理失败",
            (),
            __import__("sys").exc_info(),
        )

    rendered = JsonFormatter().format(record)
    payload = json.loads(rendered)

    assert payload["error_type"] == "ValueError"
    assert payload["error_frames"]
    assert sentinel not in rendered


def test_trace_filter_uses_none_outside_http_context() -> None:
    """非请求日志不再制造 trace=- 占位，Formatter 会直接省略该字段。"""

    record = make_record(trace_id="caller-value")

    assert TraceIdLogFilter().filter(record)
    assert record.trace_id is None
    assert "trace_id" not in json.loads(JsonFormatter().format(record))


@pytest.fixture
def restore_logging_state() -> Iterator[None]:
    """恢复统一配置会触及的 Logger，避免日志全局状态污染其他测试。"""

    logger_names = [
        "app",
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "httpx",
        "httpcore",
        "sqlalchemy",
        "alembic",
    ]
    root = logging.getLogger()
    root_state = (list(root.handlers), root.level)
    logger_states = {
        name: (list(logger.handlers), logger.level, logger.propagate, logger.disabled)
        for name in logger_names
        if (logger := logging.getLogger(name))
    }
    try:
        yield
    finally:
        for handler in list(root.handlers):
            if isinstance(handler, BackendStreamHandler):
                root.removeHandler(handler)
                handler.close()
        root.handlers = root_state[0]
        root.setLevel(root_state[1])
        for name, (handlers, level, propagate, disabled) in logger_states.items():
            logger = logging.getLogger(name)
            logger.handlers = handlers
            logger.setLevel(level)
            logger.propagate = propagate
            logger.disabled = disabled


def test_configure_logging_preserves_host_handler_and_is_idempotent(
    caplog: pytest.LogCaptureFixture,
    restore_logging_state: None,
) -> None:
    """重复初始化只保留一个自有 stderr Handler，同时不移除 pytest/caplog Handler。"""

    caplog_handler = caplog.handler
    configure_logging(log_level="debug", log_format="console")
    configure_logging(log_level="debug", log_format="console")

    root_handlers = logging.getLogger().handlers
    assert caplog_handler in root_handlers
    assert sum(isinstance(handler, BackendStreamHandler) for handler in root_handlers) == 1
    assert logging.getLogger("app").level == logging.DEBUG
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("sqlalchemy").level == logging.WARNING
    assert all(not logging.getLogger(name).handlers for name in ("app", "uvicorn"))

    logging.getLogger("app.test").debug("重复初始化检查")
    assert [record.message for record in caplog.records].count("重复初始化检查") == 1
