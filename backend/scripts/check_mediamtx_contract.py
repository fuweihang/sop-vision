"""使用隔离的 MediaMTX v1.20.1 容器验证 Cameras MVP 依赖的真实协议。"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Iterable
from contextlib import suppress
from uuid import uuid4

import httpx

MEDIAMTX_IMAGE = "bluenviron/mediamtx:1.20.1"
STARTUP_TIMEOUT_SECONDS = 15.0


def _docker(*arguments: str) -> str:
    """执行固定范围的 Docker 命令，并把失败保留为可诊断的命令错误。"""

    result = subprocess.run(
        ["docker", *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _wait_for_api(base_url: str) -> None:
    """等待临时容器的 Control API 就绪，超时后让契约门禁明确失败。"""

    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{base_url}/v3/config/paths/list", timeout=1.0)
            if response.is_success:
                return
        except httpx.RequestError:
            pass
        time.sleep(0.1)
    raise RuntimeError("MediaMTX Control API 未在规定时间内就绪。")


def _control_api_url(container_name: str) -> str:
    """读取 Docker 当前分配的随机回环端口；容器重启后端口可能变化。"""

    port_mapping = _docker("port", container_name, "9997/tcp")
    host_port = port_mapping.rsplit(":", maxsplit=1)[1]
    return f"http://127.0.0.1:{host_port}"


def _list_all(client: httpx.Client, endpoint: str, *, items_per_page: int = 2) -> list[dict]:
    """按真实 0-based 分页读取全部 items，并检查公共分页字段类型。"""

    items: list[dict] = []
    page = 0
    while True:
        response = client.get(endpoint, params={"page": page, "itemsPerPage": items_per_page})
        response.raise_for_status()
        payload = response.json()
        assert type(payload["itemCount"]) is int
        assert type(payload["pageCount"]) is int
        assert isinstance(payload["items"], list)
        items.extend(payload["items"])
        page += 1
        if page >= payload["pageCount"]:
            return items


def _assert_names_present(items: Iterable[dict], expected_names: set[str]) -> None:
    """只比较测试创建的 Path，允许官方版本保留自身默认配置。"""

    actual_names = {item.get("name") for item in items}
    assert expected_names <= actual_names


def _run_contract(base_url: str, path_names: list[str]) -> None:
    """验证配置 CRUD、分页和运行态严格布尔字段。"""

    source_url = "rtsp://192.0.2.1:554/contract-test"
    with httpx.Client(base_url=base_url, timeout=2.0) as client:
        for path_name in path_names:
            response = client.post(
                f"/v3/config/paths/replace/{path_name}",
                json={"source": source_url, "sourceOnDemand": False},
            )
            response.raise_for_status()

        detail = client.get(f"/v3/config/paths/get/{path_names[0]}")
        detail.raise_for_status()
        assert detail.json()["name"] == path_names[0]
        assert detail.json()["source"] == source_url
        assert detail.json()["sourceOnDemand"] is False

        _assert_names_present(_list_all(client, "/v3/config/paths/list"), set(path_names))

        # sourceOnDemand=false 会立即创建运行态 Path，即使文档地址没有真实 RTSP 服务。
        deadline = time.monotonic() + 5.0
        runtime_paths: list[dict] = []
        while time.monotonic() < deadline:
            runtime_paths = _list_all(client, "/v3/paths/list")
            if set(path_names) <= {item.get("name") for item in runtime_paths}:
                break
            time.sleep(0.1)
        _assert_names_present(runtime_paths, set(path_names))
        for item in runtime_paths:
            if item.get("name") in path_names:
                assert type(item["available"]) is bool
                assert type(item["online"]) is bool

        deleted = client.delete(f"/v3/config/paths/delete/{path_names[0]}")
        deleted.raise_for_status()
        assert client.get(f"/v3/config/paths/get/{path_names[0]}").status_code == 404


def main() -> int:
    """启动真实实例、验证重启丢失内存配置，并始终清理临时容器。"""

    container_name = f"sop-vision-mediamtx-contract-{uuid4().hex[:12]}"
    path_names = [str(uuid4()) for _ in range(3)]
    try:
        _docker(
            "run",
            "--detach",
            "--name",
            container_name,
            "--env",
            "MTX_API=yes",
            "--env",
            "MTX_APIADDRESS=:9997",
            "--env",
            "MTX_AUTHINTERNALUSERS_1_IPS=0.0.0.0/0",
            "--publish",
            "127.0.0.1::9997",
            MEDIAMTX_IMAGE,
        )
        base_url = _control_api_url(container_name)

        _wait_for_api(base_url)
        _run_contract(base_url, path_names)

        # Control API 只修改内存；同一容器重启后，尚未删除的测试 Path 也必须消失。
        _docker("restart", container_name)
        base_url = _control_api_url(container_name)
        _wait_for_api(base_url)
        with httpx.Client(base_url=base_url, timeout=2.0) as client:
            configured = _list_all(client, "/v3/config/paths/list", items_per_page=100)
        remaining_names = {item.get("name") for item in configured}
        assert remaining_names.isdisjoint(path_names)
    finally:
        # 容器名由本脚本生成且作用域精确；失败路径也不能污染开发环境。
        with suppress(subprocess.CalledProcessError):
            _docker("rm", "--force", container_name)

    print("MediaMTX v1.20.1 真实协议、分页、严格布尔字段与重启丢失行为验证通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
