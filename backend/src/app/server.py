"""Backend 的统一 Uvicorn 命令行启动入口。"""

import argparse
from collections.abc import Sequence

import uvicorn

from app.core.config import get_settings
from app.core.logging import configure_logging


def _port(value: str) -> int:
    """解析有效 TCP 端口，避免 Uvicorn 启动后才报告明显参数错误。"""

    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("端口必须在 1 到 65535 之间")
    return port


def _worker_count(value: str) -> int:
    """worker 至少为 1；零或负数没有可执行的服务器含义。"""

    workers = int(value)
    if workers < 1:
        raise argparse.ArgumentTypeError("worker 数量必须大于等于 1")
    return workers


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """解析最小启动参数，并阻止 Uvicorn 不支持的 reload/多 worker 组合。"""

    parser = argparse.ArgumentParser(description="启动 SOP Vision Backend")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认仅本机可访问")
    parser.add_argument("--port", type=_port, default=3001, help="监听端口，默认 3001")
    parser.add_argument("--reload", action="store_true", help="开发环境启用源码自动重载")
    parser.add_argument("--workers", type=_worker_count, default=1, help="worker 数量，默认 1")
    parsed = parser.parse_args(arguments)
    if parsed.reload and parsed.workers > 1:
        parser.error("--reload 不能与 --workers > 1 同时使用")
    return parsed


def main(arguments: Sequence[str] | None = None) -> None:
    """先加载配置和初始化日志，再把同一日志字典交给 Uvicorn。"""

    parsed = parse_arguments(arguments)
    settings = get_settings()
    log_config = configure_logging(
        log_level=settings.backend_log_level,
        log_format=settings.backend_log_format,
    )
    # 使用 import string 才能让 reload 和多 worker 子进程重新导入应用。启动调用只放在 main
    # 内，子进程导入 app.main 时不会再次创建 supervisor 或改写 pytest/宿主 Handler。
    uvicorn.run(
        "app.main:app",
        host=parsed.host,
        port=parsed.port,
        reload=parsed.reload,
        workers=parsed.workers,
        log_config=log_config,
        log_level=settings.backend_log_level,
        # 应用 middleware 已记录脱敏 path、trace、真实状态和完整耗时；关闭 Uvicorn 原生
        # request line，避免同一请求重复输出以及 query string 进入日志。
        access_log=False,
    )


if __name__ == "__main__":
    main()
