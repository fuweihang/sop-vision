"""算法服务共享的外围配置与安全日志辅助函数。"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from urllib.parse import SplitResult, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/0"
DEFAULT_WORKER_TYPES = ("detector", "tracker")


class AlgorithmConfigError(ValueError):
    """外围 TOML 不存在或不能安全地转换为运行配置。"""


class WorkerModelConfig(BaseModel):
    """一个 Worker 类型固定使用的模型配置。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_path: Path = Field(title="模型路径")

    @field_validator("model_path", mode="before")
    @classmethod
    def validate_model_path(cls, value: object) -> object:
        """拒绝空路径，避免模型库把空字符串当成隐式默认模型。"""

        if not str(value).strip():
            raise ValueError("模型路径不能为空")
        return value


class AlgorithmConfig(BaseModel):
    """Daemon、独立 Worker 和 Viewer 共用的外围配置。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    redis_url: str = Field(default=DEFAULT_REDIS_URL, min_length=1)
    workers: dict[str, WorkerModelConfig]

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, value: str) -> str:
        """只做非空检查，不限制 Redis 支持的 Unix socket 等连接形式。"""

        normalized = value.strip()
        if not normalized:
            raise ValueError("Redis 地址不能为空")
        return normalized

    def model_path_for(self, worker_type: str) -> Path:
        """返回指定 Worker 类型的模型路径，缺少配置时提供明确错误。"""

        try:
            return self.workers[worker_type].model_path
        except KeyError as error:
            raise AlgorithmConfigError(
                f"外围配置缺少 workers.{worker_type}.model_path"
            ) from error


def project_root() -> Path:
    """返回算法工程根目录，与当前工作目录无关。"""

    return Path(__file__).resolve().parents[3]


def default_config_path() -> Path:
    """返回命令行默认使用的 TOML 路径，允许环境变量统一覆盖。"""

    configured = os.getenv("ALGORITHM_CONFIG")
    return (
        Path(configured).expanduser()
        if configured
        else project_root() / "config.toml"
    )


def load_algorithm_config(
    path: Path,
    *,
    required_worker_types: tuple[str, ...] = DEFAULT_WORKER_TYPES,
) -> AlgorithmConfig:
    """读取并校验外围 TOML，同时把相对模型路径改为可直接使用的绝对路径。

    错误信息只包含文件位置和字段名，不回显 Redis 地址或 TOML 中的原始值，
    避免带用户名和密码的连接串进入日志或 API 错误响应。
    """

    config_path = path.expanduser().resolve()
    try:
        with config_path.open("rb") as file:
            payload = tomllib.load(file)
    except FileNotFoundError as error:
        raise AlgorithmConfigError(f"外围配置文件不存在：{config_path}") from error
    except (OSError, tomllib.TOMLDecodeError) as error:
        # TOMLDecodeError 的具体消息可能包含文件内容，因此这里只报告错误类型。
        raise AlgorithmConfigError(f"无法读取外围配置文件：{config_path}") from error

    try:
        config = AlgorithmConfig.model_validate(payload)
    except ValidationError as error:
        raise AlgorithmConfigError(_safe_validation_detail(error)) from error

    required = set(required_worker_types)
    configured = set(config.workers)
    missing = sorted(required - configured)
    if missing:
        fields = ", ".join(f"workers.{name}.model_path" for name in missing)
        raise AlgorithmConfigError(f"外围配置缺少字段：{fields}")
    unknown = sorted(configured - required)
    if unknown:
        fields = ", ".join(f"workers.{name}" for name in unknown)
        raise AlgorithmConfigError(f"外围配置包含未知 Worker 类型：{fields}")

    resolved_workers: dict[str, WorkerModelConfig] = {}
    for worker_type, worker in config.workers.items():
        model_path = worker.model_path.expanduser()
        if not model_path.is_absolute():
            model_path = config_path.parent / model_path
        resolved_workers[worker_type] = worker.model_copy(
            update={"model_path": model_path.resolve()}
        )
    return config.model_copy(update={"workers": resolved_workers})


def _safe_validation_detail(error: ValidationError) -> str:
    """把 Pydantic 错误转换成不包含 TOML 原始输入值的中文说明。"""

    details: list[str] = []
    for item in error.errors(include_url=False, include_input=False):
        location = ".".join(str(part) for part in item["loc"]) or "config"
        details.append(f"{location}: {item['msg']}")
    return "外围配置字段无效：" + "; ".join(details)


def redact_url(value: str) -> str:
    """在写入日志前移除 URL 中的凭据（credentials）。"""

    try:
        parsed = urlsplit(value)
    except ValueError:
        return "<invalid-url>"

    if not parsed.hostname:
        return value

    host = parsed.hostname
    if ":" in host:
        host = f"[{host}]"
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    if parsed.username is not None:
        host = f"***:***@{host}"

    return urlunsplit(
        SplitResult(parsed.scheme, host, parsed.path, parsed.query, parsed.fragment)
    )
