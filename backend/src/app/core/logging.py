"""Backend 统一日志格式、字段白名单与标准库 logging 配置。"""

import json
import logging
import logging.config
import math
import traceback
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Literal, TypedDict

BackendLogLevel = Literal["debug", "info", "warning", "error", "critical"]
BackendLogFormat = Literal["console", "json"]


class SafeExceptionFields(TypedDict):
    """可安全写入 LogRecord.extra 的异常字段。"""

    error_type: str
    error_frames: list[str]


# 映射使用完整 Logger 段前缀，避免 ``uvicorn.access_extra`` 误命中 ``uvicorn.access``。
# resolve_component 会按名称长度排序，所以越具体的业务 Logger 始终优先于父 Logger。
COMPONENT_BY_LOGGER_PREFIX: dict[str, str] = {
    "root": "backend",
    "app.factory": "backend.lifecycle",
    "app.modules.stream_gateway.services.mediamtx": "stream.gateway",
    "app.modules.cameras.application.reconciliation": "media.reconciliation",
    "app.modules.cameras.application.create": "camera.create",
    "app.modules.cameras.persistence.integrity": "camera.integrity",
    "app.core.http.access": "http.access",
    "uvicorn.access": "server.access",
    "uvicorn.error": "server",
    "uvicorn": "server",
    "sqlalchemy.engine": "database.sql",
    "alembic": "database.migration",
}

# 每个事件的顺序直接对应设计文档中的事件表。console 和 JSON 共用这张表，避免两种格式
# 因各自拼字段而逐渐产生差异。任务 2/3 只需按事件附加这里已经允许的字段。
EVENT_FIELD_ORDER: dict[str, tuple[str, ...]] = {
    "stream_gateway.io": (
        "operation",
        "outcome",
        "duration_ms",
        "error_type",
        "source_id",
        "path_count",
    ),
    "media_reconciliation.round_completed": (
        "outcome",
        "desired_count",
        "managed_path_count",
        "ensured_count",
        "released_count",
        "duration_ms",
    ),
    "media_reconciliation.round_failed": (
        "outcome",
        "desired_count",
        "managed_path_count",
        "ensured_count",
        "released_count",
        "failed_count",
        "retry_in_seconds",
        "consecutive_failures",
        "degraded_duration_seconds",
        "duration_ms",
    ),
    "media_reconciliation.recovered": (
        "outcome",
        "desired_count",
        "managed_path_count",
        "ensured_count",
        "released_count",
        "consecutive_failures",
        "degraded_duration_seconds",
        "duration_ms",
    ),
    "media_reconciliation.runner_exit": (
        "outcome",
        "timeout_seconds",
        "error_type",
        "error_frames",
    ),
    "camera.media_sync_degraded": (
        "operation",
        "outcome",
        "camera_id",
        "failed_count",
    ),
    "camera.reference_integrity_failed": (
        "integrity_issue_kind",
        "camera_id",
        "source_id",
    ),
    "http.request_completed": (
        "method",
        "path",
        "status_code",
        "duration_ms",
    ),
}

# 任务 1 暂时保留旧业务 message。这些记录还没有 event，因此使用公共字段顺序显示已有 extra；
# 未知 extra 永远不会因为遍历 record.__dict__ 而被意外输出。
FALLBACK_FIELD_ORDER: tuple[str, ...] = (
    "operation",
    "outcome",
    "duration_ms",
    "error_type",
    "error_frames",
    "camera_id",
    "source_id",
    "path_count",
    "desired_count",
    "managed_path_count",
    "ensured_count",
    "released_count",
    "failed_count",
    "retry_in_seconds",
    "consecutive_failures",
    "degraded_duration_seconds",
    "integrity_issue_kind",
    "method",
    "path",
    "status_code",
    "timeout_seconds",
)

STRING_FIELDS = frozenset(
    {
        "event",
        "trace_id",
        "operation",
        "outcome",
        "error_type",
        "camera_id",
        "source_id",
        "integrity_issue_kind",
        "method",
        "path",
    }
)
INTEGER_FIELDS = frozenset(
    {
        "duration_ms",
        "status_code",
        "path_count",
        "desired_count",
        "managed_path_count",
        "ensured_count",
        "released_count",
        "failed_count",
        "consecutive_failures",
    }
)
SECONDS_FIELDS = frozenset({"retry_in_seconds", "degraded_duration_seconds", "timeout_seconds"})

CONSOLE_FIELD_NAMES: dict[str, str] = {
    "operation": "operation",
    "outcome": "result",
    "duration_ms": "duration",
    "error_type": "error",
    "error_frames": "frames",
    "camera_id": "camera",
    "source_id": "source",
    "path_count": "paths",
    "desired_count": "desired",
    "managed_path_count": "managed",
    "ensured_count": "ensured",
    "released_count": "released",
    "failed_count": "failed",
    "retry_in_seconds": "retry",
    "consecutive_failures": "failures",
    "degraded_duration_seconds": "degraded",
    "integrity_issue_kind": "kind",
    "method": "method",
    "path": "path",
    "status_code": "status",
    "timeout_seconds": "timeout",
    "trace_id": "trace",
}

LEVEL_NAMES: dict[int, str] = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARN",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRIT",
}

# 只给固定宽度的级别列着色，正文和业务字段保持终端默认颜色，连续查看多行时更容易定位
# 严重程度。颜色不做 TTY 判断：console 格式的用途就是人读输出，因此 Docker 和重定向文件
# 也会原样包含这些 ANSI 转义码；JSON 格式完全不引用这张表。
ANSI_RESET = "\x1b[0m"
LEVEL_COLORS: dict[int, str] = {
    logging.DEBUG: "\x1b[90m",  # 灰色，弱化开发诊断信息。
    logging.INFO: "\x1b[32m",  # 绿色，表示正常业务事件。
    logging.WARNING: "\x1b[33m",  # 黄色，提示需要留意但尚未失败。
    logging.ERROR: "\x1b[31m",  # 红色，突出本次操作失败。
    logging.CRITICAL: "\x1b[1;31m",  # 粗体红色，突出进程级严重故障。
}


def safe_exception_fields(error: BaseException) -> SafeExceptionFields:
    """把未知异常压缩为类型和最多 20 个最内层代码位置。

    不读取 ``str(error)``、局部变量或源码行，也不返回异常对象。文件只保留 basename，防止
    容器路径、开发者主目录和部署目录进入日志。调用方可用 ``extra=...`` 附加返回值。
    """

    return {
        "error_type": type(error).__name__,
        "error_frames": _safe_traceback_frames(error.__traceback__),
    }


def _safe_traceback_frames(traceback_object: TracebackType | None) -> list[str]:
    """从 traceback 提取稳定位置字符串，不格式化异常消息。"""

    if traceback_object is None:
        return []
    extracted = traceback.extract_tb(traceback_object)[-20:]
    return [f"{Path(frame.filename).name}:{frame.name}:{frame.lineno}" for frame in extracted]


def resolve_component(logger_name: str) -> str:
    """按最长 Logger 段前缀返回人类可读组件名。"""

    for prefix in sorted(COMPONENT_BY_LOGGER_PREFIX, key=len, reverse=True):
        if logger_name == prefix or logger_name.startswith(f"{prefix}."):
            return COMPONENT_BY_LOGGER_PREFIX[prefix]
    if logger_name.startswith("app."):
        return logger_name.removeprefix("app.")
    return logger_name


def _timestamp(record: logging.LogRecord) -> str:
    """按进程所在地区格式化 LogRecord 创建时间。

    容器通过 ``TZ`` 选择地区，Python 会根据系统 zoneinfo 自动处理当地偏移和夏令时。
    这里只输出人读格式，不附加毫秒和时区后缀；日志采集端需要结合部署的 ``TZ`` 解释时间。
    数据库、API 和业务快照继续显式使用 UTC，不受这个展示函数影响。
    """

    return datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")


def _level_name(record: logging.LogRecord) -> str:
    """把标准级别压缩为固定显示值；自定义级别仍保留其名称。"""

    return LEVEL_NAMES.get(record.levelno, record.levelname.upper())


def _colored_console_level(record: logging.LogRecord) -> str:
    """返回固定五列的级别文本，并仅为标准日志级别添加 ANSI 颜色。"""

    # 必须先补齐可见字符宽度再包颜色；若把 ANSI 序列放进格式化表达式，Python 会把不可见
    # 的转义字符也计入列宽，导致 component 列随级别颜色长度左右漂移。
    padded_level = f"{_level_name(record):<5}"
    color = LEVEL_COLORS.get(record.levelno)
    if color is None:
        # 第三方库可能注册自定义级别。没有明确颜色含义时保留文本，避免误导排障人员。
        return padded_level
    return f"{color}{padded_level}{ANSI_RESET}"


def _visible_text(value: str) -> str:
    """转义会破坏物理单行的 C0/DEL 控制字符。"""

    parts: list[str] = []
    for character in value:
        codepoint = ord(character)
        if character == "\n":
            parts.append("\\n")
        elif character == "\r":
            parts.append("\\r")
        elif character == "\t":
            parts.append("\\t")
        elif codepoint < 32 or codepoint == 127:
            parts.append(f"\\x{codepoint:02x}")
        else:
            parts.append(character)
    return "".join(parts)


def _validated_field(record: logging.LogRecord, field_name: str) -> object | None:
    """读取并验证一个白名单字段，错误类型直接省略而不是让 Formatter 失败。"""

    value = getattr(record, field_name, None)
    if field_name in STRING_FIELDS:
        return value if isinstance(value, str) and value not in {"", "-"} else None
    if field_name in INTEGER_FIELDS:
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        return None
    if field_name in SECONDS_FIELDS:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value if value >= 0 and math.isfinite(value) else None
        return None
    if field_name == "error_frames":
        if not isinstance(value, (list, tuple)):
            return None
        if not all(isinstance(frame, str) for frame in value):
            return None
        frames = [frame for frame in value if frame not in {"", "-"}]
        return frames or None
    return None


def _safe_exception_from_record(record: logging.LogRecord) -> SafeExceptionFields | None:
    """读取第三方 Logger 的 exc_info，但不调用会拼异常文本的标准 formatException。"""

    if not record.exc_info or not isinstance(record.exc_info, tuple):
        return None
    error = record.exc_info[1]
    if not isinstance(error, BaseException):
        return None
    # 某些第三方会传入独立 traceback；优先尊重 exc_info 中的帧，同时仍只取安全位置。
    traceback_object = record.exc_info[2]
    return {
        "error_type": type(error).__name__,
        "error_frames": _safe_traceback_frames(traceback_object),
    }


def _record_fields(record: logging.LogRecord) -> dict[str, object]:
    """按事件顺序建立字段字典，并补充第三方异常的安全摘要。"""

    event_value = _validated_field(record, "event")
    # _validated_field 同时服务字符串、数值和列表字段，所以它的通用返回类型是 object。
    # event 在运行时只可能通过字符串校验；这里显式缩窄，既保留统一校验入口，也避免把未知
    # object 传给只接受 str 键的 EVENT_FIELD_ORDER。
    event = event_value if isinstance(event_value, str) else None
    order = (
        EVENT_FIELD_ORDER.get(event, FALLBACK_FIELD_ORDER)
        if event is not None
        else FALLBACK_FIELD_ORDER
    )
    fields: dict[str, object] = {}
    for field_name in order:
        value = _validated_field(record, field_name)
        if value is not None:
            fields[field_name] = value

    exception_fields = _safe_exception_from_record(record)
    if exception_fields is not None:
        # 无 event 的第三方记录允许两个安全异常字段；应用事件则严格服从事件表，防止调用方
        # 通过 exc_info 绕过该事件允许的字段集合。
        if event is None or "error_type" in order:
            fields.setdefault("error_type", exception_fields["error_type"])
        if (event is None or "error_frames" in order) and exception_fields["error_frames"]:
            fields.setdefault("error_frames", exception_fields["error_frames"])
    return fields


class ConsoleFormatter(logging.Formatter):
    """输出级别固定带 ANSI 颜色、适合终端阅读的单行日志。"""

    def format(self, record: logging.LogRecord) -> str:
        """按固定列输出 message、事件字段和当前 trace。"""

        timestamp = _timestamp(record)
        level = _colored_console_level(record)
        component = _visible_text(resolve_component(record.name))
        message = _visible_text(record.getMessage())
        # level 后保留一个分隔空格；component 自身补齐到 22 列后直接接 message，正好与
        # 设计示例中的 ``WARN  media.reconciliation  message`` 对齐。
        rendered = f"{timestamp} {level} {component:<22}{message}"

        field_parts = [
            self._format_field(name, value) for name, value in _record_fields(record).items()
        ]
        trace_id = _validated_field(record, "trace_id")
        if trace_id is not None:
            field_parts.append(self._format_field("trace_id", trace_id))
        if field_parts:
            rendered = f"{rendered}  {' '.join(field_parts)}"
        return rendered

    @staticmethod
    def _format_field(name: str, value: object) -> str:
        """应用 console 短键和单位；JSON 保持原字段名与原始数值类型。"""

        key = CONSOLE_FIELD_NAMES[name]
        if name == "duration_ms":
            return f"{key}={value}ms"
        if name in SECONDS_FIELDS:
            # 秒数字段进入 Formatter 前已经由 _validated_field 排除 bool、负数和非有限值。
            # 此断言把该运行时保证告知类型检查器，避免直接对 object 调用 float。
            assert isinstance(value, (int, float)) and not isinstance(value, bool)
            return f"{key}={float(value):.1f}s"
        if name == "error_frames":
            assert isinstance(value, list)
            return f"{key}={_visible_text(','.join(value))}"
        assert isinstance(value, (str, int))
        text = _visible_text(value) if isinstance(value, str) else str(value)
        return f"{key}={text}"


class JsonFormatter(logging.Formatter):
    """输出字段稳定、保留中文和数值类型的紧凑单行 JSON。"""

    def format(self, record: logging.LogRecord) -> str:
        """只序列化公共键和事件白名单，不展开任意 LogRecord.extra。"""

        payload: dict[str, object] = {
            "timestamp": _timestamp(record),
            "level": _level_name(record),
            "logger": record.name,
            "component": resolve_component(record.name),
            "message": record.getMessage(),
        }
        event = _validated_field(record, "event")
        if event is not None:
            payload["event"] = event
        trace_id = _validated_field(record, "trace_id")
        if trace_id is not None:
            payload["trace_id"] = trace_id
        payload.update(_record_fields(record))
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class BackendStreamHandler(logging.StreamHandler[Any]):
    """标记由本模块拥有的 stderr Handler，供重复初始化时精确替换。"""


def build_logging_config(
    *,
    log_level: BackendLogLevel,
    log_format: BackendLogFormat,
) -> dict[str, Any]:
    """构造可直接交给 logging.dictConfig 和 Uvicorn 的同一份配置。"""

    formatter_class = (
        "app.core.logging.ConsoleFormatter"
        if log_format == "console"
        else "app.core.logging.JsonFormatter"
    )
    application_level = log_level.upper()
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"backend": {"()": formatter_class}},
        "filters": {"trace_id": {"()": "app.core.http.trace.TraceIdLogFilter"}},
        "handlers": {
            "backend": {
                "class": "app.core.logging.BackendStreamHandler",
                "formatter": "backend",
                "filters": ["trace_id"],
                "level": "NOTSET",
                "stream": "ext://sys.stderr",
            }
        },
        "root": {"handlers": ["backend"], "level": "WARNING"},
        "loggers": {
            "app": {"handlers": [], "level": application_level, "propagate": True},
            "uvicorn": {"handlers": [], "level": application_level, "propagate": True},
            "uvicorn.error": {
                "handlers": [],
                "level": application_level,
                "propagate": True,
            },
            "uvicorn.access": {
                "handlers": [],
                "level": application_level,
                "propagate": True,
            },
            "httpx": {"handlers": [], "level": "WARNING", "propagate": True},
            "httpcore": {"handlers": [], "level": "WARNING", "propagate": True},
            "sqlalchemy": {"handlers": [], "level": "WARNING", "propagate": True},
            "alembic": {"handlers": [], "level": "INFO", "propagate": True},
        },
    }


def configure_logging(
    *,
    log_level: BackendLogLevel,
    log_format: BackendLogFormat,
) -> dict[str, Any]:
    """应用统一配置并保留 pytest 或嵌入式宿主已经安装的 Handler。

    标准 ``dictConfig`` 会替换 root Handler。这里在应用配置前记住非本模块 Handler，随后只把
    缺失的实例放回 root；本模块旧 Handler 不保留，因此重复调用始终只有一个 stderr 输出。
    返回的原字典会继续传给 Uvicorn，让 reload/worker 子进程应用完全相同的配置。
    """

    root = logging.getLogger()
    host_handlers = [
        handler for handler in root.handlers if not isinstance(handler, BackendStreamHandler)
    ]
    config = build_logging_config(log_level=log_level, log_format=log_format)
    logging.config.dictConfig(config)
    for handler in host_handlers:
        if handler not in root.handlers:
            root.addHandler(handler)
    return config
