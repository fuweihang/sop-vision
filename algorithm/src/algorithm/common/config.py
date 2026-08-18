"""算法服务共享的配置辅助函数。"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import SplitResult, urlsplit, urlunsplit


def project_root() -> Path:
    """返回算法工程根目录，与当前工作目录无关。"""

    return Path(__file__).resolve().parents[3]


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
