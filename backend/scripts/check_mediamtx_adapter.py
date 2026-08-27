"""使用隔离的 MediaMTX v1.20.1 容器验证真实 Stream Gateway Adapter。"""

from __future__ import annotations

import asyncio
import subprocess
import time
from contextlib import suppress
from uuid import UUID, uuid4

import httpx

from app.modules.stream_gateway.ports import DesiredSource
from app.modules.stream_gateway.services.mediamtx import MediaMTXAdapter

MEDIAMTX_IMAGE = "bluenviron/mediamtx:1.20.1"
STARTUP_TIMEOUT_SECONDS = 15.0
RUNTIME_APPEAR_TIMEOUT_SECONDS = 5.0


def _docker(*arguments: str) -> str:
    """执行固定范围 Docker 命令，并保留失败供门禁输出准确诊断。"""

    result = subprocess.run(
        ["docker", *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _control_api_url(container_name: str) -> str:
    """读取 Docker 随机分配的回环端口，避免占用或污染共享开发实例。"""

    port_mapping = _docker("port", container_name, "9997/tcp")
    host_port = port_mapping.rsplit(":", maxsplit=1)[1]
    return f"http://127.0.0.1:{host_port}"


def _wait_for_api(base_url: str) -> None:
    """仅等待临时容器 Control API 启动，不把启动轮询混入 Adapter 重试策略。"""

    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    with httpx.Client(base_url=base_url, timeout=1.0, trust_env=False) as client:
        while time.monotonic() < deadline:
            try:
                response = client.get(
                    "/v3/config/paths/list",
                    params={"page": 0, "itemsPerPage": 100},
                )
                if response.is_success:
                    return
            except httpx.RequestError:
                pass
            time.sleep(0.1)
    raise RuntimeError("MediaMTX Control API 未在规定时间内就绪。")


async def _wait_for_runtime_paths(
    adapter: MediaMTXAdapter,
    expected_ids: set[UUID],
) -> None:
    """等待真实 MediaMTX 建立运行态 Path，并验证 Adapter 完整快照可观察到它们。"""

    deadline = time.monotonic() + RUNTIME_APPEAR_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        snapshot = await adapter.fetch_runtime_path_snapshot()
        actual_names = {path.name for path in snapshot.paths}
        if {str(source_id) for source_id in expected_ids} <= actual_names:
            return
        # 轮询属于门禁等待真实实例异步建 Path，不是生产 Adapter 内部自动重试。
        await asyncio.sleep(0.1)
    raise RuntimeError("MediaMTX 未在规定时间内建立全部测试运行态 Path。")


async def _run_adapter_contract(base_url: str) -> None:
    """验证覆盖、配置/运行快照、幂等删除和带路径前缀 WHEP 地址。"""

    adapter = MediaMTXAdapter(
        control_api_url=base_url,
        request_timeout=2.0,
        public_webrtc_base_url="https://vision.example.invalid/media/webrtc/",
    )
    source_ids = [uuid4() for _ in range(3)]
    desired_sources = [
        DesiredSource(
            source_id=source_id,
            # RFC 5737 文档网段不可路由，但 sourceOnDemand=false 足以让真实 MTX 建立离线
            # 运行态 Path；门禁不依赖现场 Camera 或外部网络。
            source_url=f"rtsp://192.0.2.{index + 1}:554/adapter-test",
        )
        for index, source_id in enumerate(source_ids)
    ]

    try:
        for desired_source in desired_sources:
            await adapter.ensure_path(desired_source)

        configured = await adapter.fetch_config_path_snapshot()
        configured_by_name = {path.name: path for path in configured.paths}
        for desired_source in desired_sources:
            actual = configured_by_name[desired_source.path_name]
            assert actual.source_url == desired_source.source_url
            assert actual.source_on_demand is False

        await _wait_for_runtime_paths(adapter, set(source_ids))

        # 第二次 replace 同一 UUID 必须覆盖配置，而不是创建另一个 Path。
        updated = DesiredSource(
            source_id=source_ids[0],
            source_url="rtsp://192.0.2.200:554/adapter-updated",
        )
        await adapter.ensure_path(updated)
        configured_after_replace = await adapter.fetch_config_path_snapshot()
        updated_paths = {path.name: path for path in configured_after_replace.paths}
        assert updated_paths[str(source_ids[0])].source_url == updated.source_url

        expected_whep = f"https://vision.example.invalid/media/webrtc/{source_ids[0]}/whep"
        assert adapter.whep_url_for(source_ids[0]) == expected_whep

        await adapter.release_path(source_ids[0])
        await adapter.release_path(source_ids[0])
        configured_after_delete = await adapter.fetch_config_path_snapshot()
        assert str(source_ids[0]) not in {path.name for path in configured_after_delete.paths}
    finally:
        await adapter.close()


def main() -> int:
    """启动隔离实例、运行真实 Adapter 契约，并在所有失败路径清理容器。"""

    container_name = f"sop-vision-mediamtx-adapter-{uuid4().hex[:12]}"
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
        asyncio.run(_run_adapter_contract(base_url))
    finally:
        # 容器名由脚本生成且精确限定；即使断言或网络调用失败也不能污染开发环境。
        with suppress(subprocess.CalledProcessError):
            _docker("rm", "--force", container_name)

    print("MediaMTX v1.20.1 真实 Adapter 覆盖、快照、删除和 WHEP 契约验证通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
