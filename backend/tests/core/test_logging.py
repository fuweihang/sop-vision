"""统一日志 Formatter、字段安全边界和重复初始化测试。"""

import asyncio
import json
import logging
import os
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from io import StringIO

import pytest
from sqlalchemy import create_engine, text

from app.core.http.trace import TraceIdLogFilter
from app.core.logging import (
    BackendStreamHandler,
    ConsoleFormatter,
    JsonFormatter,
    configure_logging,
    migration_logging_context,
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


def test_console_formatter_keeps_colored_prefix_and_plain_body_on_one_line(
    set_process_timezone: Callable[[str], None],
) -> None:
    """console 前缀着色、正文无颜色，并继续转义可能伪造日志行的控制字符。"""

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
        "\x1b[94m[08-28 16:49:08]\x1b[0m\x1b[33m[WARN]\x1b[0m"
        "\x1b[36m[camera.create]\x1b[0m"
        "Camera 已保存\\n但媒体操作\\t未全部成功: "
        "operation=post_commit_media_sync result=degraded camera=camera-1 failed=0 "
        "trace=tr_abc123"
    )
    assert len(rendered.splitlines()) == 1


def test_console_and_json_formatters_follow_the_same_container_timezone(
    set_process_timezone: Callable[[str], None],
) -> None:
    """两种输出读取同一个 ``TZ``，console 省略年份而 JSON 保留完整日期。"""

    set_process_timezone("Asia/Shanghai")
    record = make_record()

    console_header = ConsoleFormatter().format(record).splitlines()[0]
    json_timestamp = json.loads(JsonFormatter().format(record))["timestamp"]

    assert console_header.startswith("\x1b[94m[08-28 16:49:08]\x1b[0m")
    assert json_timestamp == "2026-08-28 16:49:08"
    assert all(marker not in console_header for marker in (".431", "Z", "+08:00", "CST"))


@pytest.mark.parametrize(
    ("level", "name", "color"),
    [
        (logging.DEBUG, "DEBUG", "\x1b[90m"),
        (logging.INFO, "INFO", "\x1b[32m"),
        (logging.WARNING, "WARN", "\x1b[33m"),
        (logging.ERROR, "ERROR", "\x1b[31m"),
        (logging.CRITICAL, "CRIT", "\x1b[1;31m"),
    ],
)
def test_console_colors_standard_levels_but_json_remains_plain(
    level: int,
    name: str,
    color: str,
) -> None:
    """五个标准级别固定着色，JSON 级别和值中不得混入 ANSI 控制码。"""

    record = make_record(level=level)

    console = ConsoleFormatter().format(record)
    json_output = JsonFormatter().format(record)

    assert f"{color}[{name}]\x1b[0m\x1b[36m[camera.create]\x1b[0m" in console
    # console 的时间、级别和组件各自重置颜色，后续正文不能继承任何 ANSI 样式。
    assert console.count("\x1b[0m") == 3
    assert "\x1b" not in console.rsplit("\x1b[0m", maxsplit=1)[1]
    assert "\x1b" not in json_output
    assert json.loads(json_output)["level"] == name


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


def test_http_access_event_keeps_real_status_outcome_and_field_order() -> None:
    """HTTP 状态和最终结果必须同时保留，避免把流式中断的 200 伪装成 500。"""

    record = make_record(
        name="app.core.http.access",
        message="HTTP 响应发送中断",
        level=logging.ERROR,
        event="http.request_completed",
        method="GET",
        path="/api/v1/export",
        status_code=200,
        outcome="response_interrupted",
        duration_ms=320,
        trace_id="tr_stream",
    )

    console = ConsoleFormatter().format(record)
    payload = json.loads(JsonFormatter().format(record))

    assert (
        "method=GET path=/api/v1/export status=200 result=response_interrupted "
        "duration=320ms trace=tr_stream"
    ) in console
    assert list(payload)[-6:] == [
        "trace_id",
        "method",
        "path",
        "status_code",
        "outcome",
        "duration_ms",
    ]
    assert payload["status_code"] == 200
    assert payload["outcome"] == "response_interrupted"


@pytest.mark.parametrize(
    ("logger_name", "component"),
    [
        ("root", "backend"),
        ("app.factory", "backend.lifecycle"),
        ("app.modules.cameras.application.create.child", "camera.create"),
        ("app.modules.cameras.application.detail.child", "camera.detail"),
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


def test_camera_detail_invalid_event_uses_registered_safe_fields() -> None:
    """详情聚合损坏事件只输出固定操作、结果和 Camera ID。"""

    sentinel = "camera-detail-log-secret"
    record = make_record(
        name="app.modules.cameras.application.detail",
        level=logging.ERROR,
        message="Camera 详情聚合数据无效",
        event="camera.detail_aggregate_invalid",
        operation="get_camera",
        outcome="failed",
        camera_id="00000000-0000-4000-8000-000000000001",
        password=sentinel,
        source_id="should-not-be-rendered",
    )

    console = ConsoleFormatter().format(record)
    payload = json.loads(JsonFormatter().format(record))

    assert payload["component"] == "camera.detail"
    assert list(payload)[-4:] == ["event", "operation", "outcome", "camera_id"]
    assert "operation=get_camera result=failed" in console
    assert "source=" not in console
    assert sentinel not in console
    assert sentinel not in json.dumps(payload)


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
        "sqlalchemy.engine",
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
    configure_logging(log_level="debug", log_format="console", database_echo=False)
    configure_logging(log_level="debug", log_format="console", database_echo=False)

    root_handlers = logging.getLogger().handlers
    assert caplog_handler in root_handlers
    assert sum(isinstance(handler, BackendStreamHandler) for handler in root_handlers) == 1
    assert logging.getLogger("app").level == logging.DEBUG
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("sqlalchemy").level == logging.WARNING
    assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING
    assert all(not logging.getLogger(name).handlers for name in ("app", "uvicorn"))
    assert logging.getLogger("uvicorn.access").level == logging.CRITICAL
    assert logging.getLogger("uvicorn.access").propagate is False

    logging.getLogger("app.test").debug("重复初始化检查")
    assert [record.message for record in caplog.records].count("重复初始化检查") == 1


def test_database_echo_only_enables_sqlalchemy_engine(
    restore_logging_state: None,
) -> None:
    """数据库调试不能顺带打开连接池、httpx 或其他第三方 DEBUG/INFO。"""

    configure_logging(log_level="debug", log_format="json", database_echo=True)

    assert logging.getLogger("app").level == logging.DEBUG
    assert logging.getLogger("sqlalchemy").level == logging.WARNING
    assert logging.getLogger("sqlalchemy.engine").level == logging.INFO
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING

    # 再次关闭必须显式恢复 engine Logger；只修改父 Logger 会让同一进程残留 INFO。
    configure_logging(log_level="debug", log_format="json", database_echo=False)
    assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING


@pytest.mark.parametrize("formatter", [ConsoleFormatter(), JsonFormatter()])
def test_sqlalchemy_hides_bound_parameters_in_unified_output(
    formatter: logging.Formatter,
) -> None:
    """真实 SQLAlchemy 记录经过两种 Formatter 时都不能包含绑定参数值。"""

    secret_parameter = "sql-parameter-must-not-leak"
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    logger = logging.getLogger("sqlalchemy.engine")
    previous_state = (list(logger.handlers), logger.level, logger.propagate)
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    engine = create_engine("sqlite://", echo=False, hide_parameters=True)

    try:
        with engine.connect() as connection:
            connection.execute(
                text("SELECT :private_value"),
                {"private_value": secret_parameter},
            )
    finally:
        engine.dispose()
        logger.handlers = previous_state[0]
        logger.setLevel(previous_state[1])
        logger.propagate = previous_state[2]
        handler.close()

    rendered = stream.getvalue()
    assert secret_parameter not in rendered
    assert "SQL parameters hidden due to hide_parameters=True" in rendered


@pytest.mark.parametrize("formatter", [ConsoleFormatter(), JsonFormatter()])
def test_database_url_in_third_party_exception_is_not_rendered(
    formatter: logging.Formatter,
) -> None:
    """数据库异常即使携带完整 URL，两种统一格式也只能输出安全异常摘要。"""

    password = "database-password-must-not-leak"
    database_url = f"postgresql+psycopg://user:{password}@database/sop_vision"
    try:
        raise RuntimeError(database_url)
    except RuntimeError:
        record = logging.LogRecord(
            "sqlalchemy.engine",
            logging.ERROR,
            __file__,
            1,
            "数据库操作失败",
            (),
            __import__("sys").exc_info(),
        )

    rendered = formatter.format(record)
    assert password not in rendered
    assert database_url not in rendered
    assert "RuntimeError" in rendered


def test_migration_logging_installs_one_handler_and_restores_levels(
    restore_logging_state: None,
) -> None:
    """独立迁移进程连续执行命令时只安装一次 Handler，并恢复显式级别。"""

    root = logging.getLogger()
    root.handlers = []
    root.setLevel(logging.ERROR)
    expected_levels = {
        "alembic": logging.ERROR,
        "sqlalchemy": logging.DEBUG,
        "sqlalchemy.engine": logging.CRITICAL,
    }
    for name, level in expected_levels.items():
        logging.getLogger(name).setLevel(level)

    with migration_logging_context(log_format="json", database_echo=True):
        handlers = root.handlers
        assert sum(isinstance(handler, BackendStreamHandler) for handler in handlers) == 1
        assert isinstance(handlers[0].formatter, JsonFormatter)
        assert root.level == logging.WARNING
        assert logging.getLogger("alembic").level == logging.INFO
        assert logging.getLogger("sqlalchemy").level == logging.WARNING
        assert logging.getLogger("sqlalchemy.engine").level == logging.INFO

    assert root.level == logging.ERROR
    assert {name: logging.getLogger(name).level for name in expected_levels} == expected_levels

    # Handler 有意保留到短生命周期 CLI 退出；第二条命令会复用它，不能重复安装。
    with migration_logging_context(log_format="json", database_echo=False):
        assert sum(isinstance(handler, BackendStreamHandler) for handler in root.handlers) == 1
        assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING

    assert {name: logging.getLogger(name).level for name in expected_levels} == expected_levels


def test_migration_logging_preserves_host_handlers_and_restores_levels(
    restore_logging_state: None,
) -> None:
    """pytest/应用已有 Handler 时，迁移只能临时改 Logger 级别。"""

    root = logging.getLogger()
    host_handlers = list(root.handlers)
    assert host_handlers
    expected_levels = {
        "alembic": logging.CRITICAL,
        "sqlalchemy": logging.ERROR,
        "sqlalchemy.engine": logging.DEBUG,
    }
    for name, level in expected_levels.items():
        logging.getLogger(name).setLevel(level)

    with migration_logging_context(log_format="console", database_echo=False):
        assert root.handlers == host_handlers
        assert all(not isinstance(handler, BackendStreamHandler) for handler in root.handlers)
        assert logging.getLogger("alembic").level == logging.INFO
        assert logging.getLogger("sqlalchemy").level == logging.WARNING
        assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING

    assert root.handlers == host_handlers
    assert {name: logging.getLogger(name).level for name in expected_levels} == expected_levels


@pytest.mark.parametrize("error_type", [RuntimeError, asyncio.CancelledError])
def test_migration_logging_restores_levels_after_failure_or_cancellation(
    error_type: type[BaseException],
    restore_logging_state: None,
) -> None:
    """迁移失败或任务取消都必须经过 finally 恢复宿主 Logger 级别。"""

    expected_levels = {
        "alembic": logging.ERROR,
        "sqlalchemy": logging.CRITICAL,
        "sqlalchemy.engine": logging.DEBUG,
    }
    for name, level in expected_levels.items():
        logging.getLogger(name).setLevel(level)

    with pytest.raises(error_type):
        with migration_logging_context(log_format="console", database_echo=True):
            raise error_type()

    assert {name: logging.getLogger(name).level for name in expected_levels} == expected_levels
