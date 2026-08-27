"""MediaMTX v1.20.1 Control API Adapter。"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar
from uuid import RFC_4122, UUID

import httpx

from app.core.http import get_trace_id
from app.modules.stream_gateway.ports import (
    ConfiguredPath,
    ConfiguredPathSnapshot,
    DesiredSource,
    RuntimePath,
    RuntimePathSnapshot,
    StreamGatewayInvalidResponseError,
    StreamGatewayUnavailableError,
    _validate_uuid4,
)
from app.modules.stream_gateway.urls import build_whep_url

logger = logging.getLogger(__name__)

SNAPSHOT_TOTAL_BUDGET_SECONDS = 0.5
SNAPSHOT_ITEMS_PER_PAGE = 100

PathT = TypeVar("PathT", RuntimePath, ConfiguredPath)


class _ControlApiUnavailable(Exception):
    """Adapter 内部控制流标记；故意不保存原始 HTTP 异常或响应。"""


class _ControlApiInvalidResponse(Exception):
    """Adapter 内部控制流标记；故意不保存原始响应内容。"""


class MediaMTXAdapter:
    """实现完整 ``StreamGatewayPort`` 的 lifespan 级 HTTP Adapter。

    一个实例复用一个 ``httpx.AsyncClient`` 连接池。Adapter 只处理锁定协议、总预算、错误分类、
    日志脱敏和 URL 拼接；它不读取 Camera、重试业务操作或缓存任何 Desired State。
    """

    def __init__(
        self,
        *,
        control_api_url: str,
        request_timeout: float,
        public_webrtc_base_url: str,
    ) -> None:
        # Settings 已在应用构造前完成 URL 校验。尾斜杠让相对 v3 路径始终拼到主机根目录，
        # 同时避免 httpx 把最后一个路径段当成文件名替换。
        self._client = httpx.AsyncClient(
            base_url=f"{control_api_url.rstrip('/')}/",
            timeout=request_timeout,
            # Control API 属于部署内部边界；不继承环境 HTTP_PROXY，避免把包含 RTSP 凭据的
            # replace 请求意外转发给外部代理。需要代理的部署应在明确受控的网络层处理。
            trust_env=False,
        )
        self._public_webrtc_base_url = public_webrtc_base_url

    async def close(self) -> None:
        """关闭共享连接池；重复关闭由 httpx 保持幂等。"""

        await self._client.aclose()

    async def fetch_runtime_path_snapshot(self) -> RuntimePathSnapshot:
        """在 500ms 总预算内读取并校验全部运行态分页。"""

        started_at = time.monotonic()
        invalid_response = False
        try:
            async with asyncio.timeout(SNAPSHOT_TOTAL_BUDGET_SECONDS):
                paths = await self._fetch_all_pages(
                    "v3/paths/list",
                    parse_item=self._parse_runtime_path,
                )
            snapshot = RuntimePathSnapshot(paths=paths, checked_at=datetime.now(UTC))
        except (_ControlApiUnavailable, TimeoutError):
            self._log_io(
                operation="fetch_runtime_snapshot",
                outcome="unavailable",
                started_at=started_at,
                error_category=StreamGatewayUnavailableError.__name__,
            )
        except _ControlApiInvalidResponse:
            invalid_response = True
            self._log_io(
                operation="fetch_runtime_snapshot",
                outcome="invalid_response",
                started_at=started_at,
                error_category=StreamGatewayInvalidResponseError.__name__,
            )
        else:
            self._log_io(
                operation="fetch_runtime_snapshot",
                outcome="success",
                started_at=started_at,
                path_count=len(snapshot.paths),
            )
            return snapshot

        # 在 except 作用域外创建公共异常，避免隐式 __context__ 挂接含 URL 的 httpx 异常。
        if invalid_response:
            raise StreamGatewayInvalidResponseError()
        raise StreamGatewayUnavailableError()

    async def fetch_config_path_snapshot(self) -> ConfiguredPathSnapshot:
        """在 500ms 总预算内读取全部配置，并隔离非受管 Path 字段。"""

        started_at = time.monotonic()
        invalid_response = False
        try:
            async with asyncio.timeout(SNAPSHOT_TOTAL_BUDGET_SECONDS):
                paths = await self._fetch_all_pages(
                    "v3/config/paths/list",
                    parse_item=self._parse_configured_path,
                )
            snapshot = ConfiguredPathSnapshot(paths=paths, checked_at=datetime.now(UTC))
        except (_ControlApiUnavailable, TimeoutError):
            self._log_io(
                operation="fetch_config_snapshot",
                outcome="unavailable",
                started_at=started_at,
                error_category=StreamGatewayUnavailableError.__name__,
            )
        except _ControlApiInvalidResponse:
            invalid_response = True
            self._log_io(
                operation="fetch_config_snapshot",
                outcome="invalid_response",
                started_at=started_at,
                error_category=StreamGatewayInvalidResponseError.__name__,
            )
        else:
            self._log_io(
                operation="fetch_config_snapshot",
                outcome="success",
                started_at=started_at,
                path_count=len(snapshot.paths),
            )
            return snapshot

        if invalid_response:
            raise StreamGatewayInvalidResponseError()
        raise StreamGatewayUnavailableError()

    async def ensure_path(self, desired_source: DesiredSource) -> None:
        """使用 replace 语义把一个 UUID Path 收敛到调用方最新 Desired State。"""

        started_at = time.monotonic()
        try:
            response = await self._request(
                "POST",
                f"v3/config/paths/replace/{desired_source.path_name}",
                json={
                    "source": desired_source.source_url,
                    "sourceOnDemand": desired_source.source_on_demand,
                },
            )
            if not response.is_success:
                raise _ControlApiUnavailable
        except _ControlApiUnavailable:
            self._log_io(
                operation="ensure_path",
                outcome="unavailable",
                started_at=started_at,
                path_count=1,
                error_category=StreamGatewayUnavailableError.__name__,
                source_id=desired_source.source_id,
            )
        else:
            self._log_io(
                operation="ensure_path",
                outcome="success",
                started_at=started_at,
                path_count=1,
                source_id=desired_source.source_id,
            )
            return

        raise StreamGatewayUnavailableError()

    async def release_path(self, source_id: UUID) -> None:
        """删除同名 Path；404 表示目标已经收敛为不存在，因此按幂等成功处理。"""

        _validate_uuid4(source_id)
        started_at = time.monotonic()
        try:
            response = await self._request(
                "DELETE",
                f"v3/config/paths/delete/{source_id}",
            )
            if response.status_code != 404 and not response.is_success:
                raise _ControlApiUnavailable
        except _ControlApiUnavailable:
            self._log_io(
                operation="release_path",
                outcome="unavailable",
                started_at=started_at,
                path_count=1,
                error_category=StreamGatewayUnavailableError.__name__,
                source_id=source_id,
            )
        else:
            self._log_io(
                operation="release_path",
                outcome="success",
                started_at=started_at,
                path_count=1,
                source_id=source_id,
            )
            return

        raise StreamGatewayUnavailableError()

    def whep_url_for(self, source_id: UUID) -> str:
        """只拼接公开基础地址与 UUID Path，不探测当前媒体状态。"""

        return build_whep_url(self._public_webrtc_base_url, source_id)

    async def _fetch_all_pages(
        self,
        endpoint: str,
        *,
        parse_item: Callable[[dict[str, Any]], PathT],
    ) -> tuple[PathT, ...]:
        """按 0-based 页读取一份计数冻结、名称唯一的完整快照。"""

        first_payload = await self._get_json_page(endpoint, page=0)
        item_count, page_count, first_items = _parse_page(first_payload)

        if item_count == 0:
            if page_count != 0 or first_items:
                raise _ControlApiInvalidResponse
            return ()
        if page_count < 1 or not first_items:
            raise _ControlApiInvalidResponse

        raw_items = list(first_items)
        for page in range(1, page_count):
            payload = await self._get_json_page(endpoint, page=page)
            current_item_count, current_page_count, items = _parse_page(payload)
            # 第一页是本次不可变观察的计数基线。读取期间任何计数漂移都使整份快照失效，
            # 不能把前后两个时刻的分页拼成看似完整的数据。
            if current_item_count != item_count or current_page_count != page_count or not items:
                raise _ControlApiInvalidResponse
            raw_items.extend(items)

        if len(raw_items) != item_count:
            raise _ControlApiInvalidResponse

        parsed_items: list[PathT] = []
        names: set[str] = set()
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                raise _ControlApiInvalidResponse
            name = raw_item.get("name")
            if not isinstance(name, str) or not name or name in names:
                raise _ControlApiInvalidResponse
            names.add(name)
            parsed_items.append(parse_item(raw_item))
        return tuple(parsed_items)

    async def _get_json_page(self, endpoint: str, *, page: int) -> Any:
        """读取一页 JSON；状态、网络和 JSON 错误在进入公共错误前先脱敏。"""

        response = await self._request(
            "GET",
            endpoint,
            params={"page": page, "itemsPerPage": SNAPSHOT_ITEMS_PER_PAGE},
        )
        if not response.is_success:
            raise _ControlApiUnavailable

        invalid_json = False
        try:
            payload = response.json()
        except (TypeError, ValueError):
            invalid_json = True
            payload = None
        if invalid_json:
            raise _ControlApiInvalidResponse
        return payload

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """发送单次请求且不重试；不让原始 ``RequestError`` 越过 Adapter。"""

        failed = False
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.RequestError:
            failed = True
            response = None
        if failed or response is None:
            raise _ControlApiUnavailable
        return response

    @staticmethod
    def _parse_runtime_path(item: dict[str, Any]) -> RuntimePath:
        """只把严格 JSON ``true`` 视为真；其他值仅令该 Path 离线。"""

        return RuntimePath(
            name=item["name"],
            available=item.get("available") is True,
            online=item.get("online") is True,
        )

    @staticmethod
    def _parse_configured_path(item: dict[str, Any]) -> ConfiguredPath:
        """受管字段异常保留为未知；非受管 Path 完全不读取无关配置。"""

        name = item["name"]
        if not _is_managed_path_name(name):
            return ConfiguredPath(name=name, source_url=None, source_on_demand=None)

        source = item.get("source")
        source_on_demand = item.get("sourceOnDemand")
        return ConfiguredPath(
            name=name,
            source_url=source if isinstance(source, str) else None,
            source_on_demand=source_on_demand if type(source_on_demand) is bool else None,
        )

    @staticmethod
    def _log_io(
        *,
        operation: str,
        outcome: str,
        started_at: float,
        path_count: int = 0,
        error_category: str = "-",
        source_id: UUID | None = None,
    ) -> None:
        """同时输出控制台可见 key=value 文本和可供测试读取的结构化字段。"""

        duration_ms = max(0, round((time.monotonic() - started_at) * 1000))
        source_id_text = str(source_id) if source_id is not None else "-"
        trace_id = get_trace_id() or "-"
        extra = {
            "operation": operation,
            "outcome": outcome,
            "duration_ms": duration_ms,
            "path_count": path_count,
            "error_category": error_category,
            "source_id": source_id_text,
            "trace_id": trace_id,
        }
        level = logging.INFO if outcome == "success" else logging.WARNING
        logger.log(
            level,
            (
                "stream_gateway operation=%s outcome=%s duration_ms=%d path_count=%d "
                "error_category=%s source_id=%s trace_id=%s"
            ),
            operation,
            outcome,
            duration_ms,
            path_count,
            error_category,
            source_id_text,
            trace_id,
            extra=extra,
        )


def _parse_page(payload: Any) -> tuple[int, int, list[Any]]:
    """校验 MediaMTX 公共分页外壳，严格拒绝 bool 冒充整数。"""

    if not isinstance(payload, dict):
        raise _ControlApiInvalidResponse
    item_count = payload.get("itemCount")
    page_count = payload.get("pageCount")
    items = payload.get("items")
    if (
        type(item_count) is not int
        or item_count < 0
        or type(page_count) is not int
        or page_count < 0
        or not isinstance(items, list)
    ):
        raise _ControlApiInvalidResponse
    return item_count, page_count, items


def _is_managed_path_name(name: str) -> bool:
    """仅识别小写、带连字符、RFC variant 正确的 UUID v4 Path 名称。"""

    try:
        source_id = UUID(name)
    except (ValueError, AttributeError):
        return False
    return source_id.version == 4 and source_id.variant == RFC_4122 and str(source_id) == name
