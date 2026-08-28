"""Backend 统一 Uvicorn 启动入口测试。"""

from typing import Any

import pytest

from app import server


def test_main_configures_logging_before_starting_uvicorn(monkeypatch) -> None:
    """CLI 参数和同一份日志配置必须完整传给 Uvicorn。"""

    call_order: list[str] = []
    logging_config = {"version": 1, "marker": "same-object"}
    run_calls: list[tuple[str, dict[str, Any]]] = []

    class StubSettings:
        backend_log_level = "debug"
        backend_log_format = "json"
        database_echo = True

    monkeypatch.setattr(server, "get_settings", lambda: StubSettings())

    def configure_logging(
        *,
        log_level: str,
        log_format: str,
        database_echo: bool,
    ) -> dict[str, Any]:
        call_order.append(f"logging:{log_level}:{log_format}:{database_echo}")
        return logging_config

    def run(application: str, **kwargs: Any) -> None:
        call_order.append("uvicorn")
        run_calls.append((application, kwargs))

    monkeypatch.setattr(server, "configure_logging", configure_logging)
    monkeypatch.setattr(server.uvicorn, "run", run)

    server.main(["--host", "0.0.0.0", "--port", "3100", "--workers", "3"])

    assert call_order == ["logging:debug:json:True", "uvicorn"]
    assert run_calls == [
        (
            "app.main:app",
            {
                "host": "0.0.0.0",
                "port": 3100,
                "reload": False,
                "workers": 3,
                "log_config": logging_config,
                "log_level": "debug",
                "access_log": False,
            },
        )
    ]


def test_main_uses_safe_local_defaults(monkeypatch) -> None:
    """不传参数时只监听本机 3001，并使用单 worker。"""

    class StubSettings:
        backend_log_level = "info"
        backend_log_format = "console"
        database_echo = False

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(server, "get_settings", lambda: StubSettings())
    monkeypatch.setattr(
        server,
        "configure_logging",
        lambda **_kwargs: {"version": 1},
    )
    monkeypatch.setattr(server.uvicorn, "run", lambda _application, **kwargs: calls.append(kwargs))

    server.main([])

    assert calls[0]["host"] == "127.0.0.1"
    assert calls[0]["port"] == 3001
    assert calls[0]["workers"] == 1
    assert calls[0]["reload"] is False


@pytest.mark.parametrize(
    "arguments",
    [
        ["--reload", "--workers", "2"],
        ["--workers", "0"],
        ["--port", "0"],
    ],
)
def test_invalid_server_arguments_fail_before_loading_settings(
    arguments: list[str],
    monkeypatch,
) -> None:
    """冲突或越界参数在配置日志和创建 Uvicorn supervisor 前直接退出。"""

    monkeypatch.setattr(
        server,
        "get_settings",
        lambda: pytest.fail("非法参数不应加载应用配置"),
    )
    monkeypatch.setattr(
        server.uvicorn,
        "run",
        lambda *_args, **_kwargs: pytest.fail("非法参数不应启动 Uvicorn"),
    )

    with pytest.raises(SystemExit) as error:
        server.main(arguments)

    assert error.value.code == 2
