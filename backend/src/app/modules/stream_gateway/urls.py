"""MediaMTX 上游 RTSP 地址编码与公开 WHEP 地址构造。"""

from ipaddress import IPv4Address
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import RFC_4122, UUID


def _encode_query(query: str) -> str:
    """编码 query 的名称和值，同时保留 `&` 和 `=` 分隔语义。"""

    pairs: list[str] = []
    for pair in query.split("&"):
        name, separator, value = pair.partition("=")
        encoded_name = quote(name, safe="")
        pairs.append(f"{encoded_name}={quote(value, safe='')}" if separator else encoded_name)
    return "&".join(pairs)


def build_mediamtx_source_url(
    *,
    username: str,
    password: str,
    ip_address: IPv4Address,
    rtsp_port: int,
    url_suffix: str,
) -> str:
    """按 URI 组件编码发给 MediaMTX 的 RTSP URL。

    `url_suffix` 已由 Camera 领域规范化；这里保留 `/`、query 的 `?`、`&`、`=` 结构，其余保留
    字符作为数据百分号编码。本函数不会替换 CameraDetail 使用的展示 URL。
    """

    if not username or not password:
        raise ValueError("RTSP 用户名和密码不能为空。")
    if not 1 <= rtsp_port <= 65535:
        raise ValueError("RTSP 端口必须在 1-65535 之间。")
    if not url_suffix or url_suffix.startswith("/"):
        raise ValueError("URL 后缀必须是已规范化的非空文本。")

    path, separator, query = url_suffix.partition("?")
    encoded_suffix = quote(path, safe="/")
    if separator:
        encoded_suffix = f"{encoded_suffix}?{_encode_query(query)}"

    return (
        f"rtsp://{quote(username, safe='')}:{quote(password, safe='')}@"
        f"{ip_address}:{rtsp_port}/{encoded_suffix}"
    )


def build_whep_url(public_base_url: str, source_id: UUID) -> str:
    """保留公开地址路径前缀并追加标准 UUID Path 与 `/whep`。"""

    if source_id.version != 4 or source_id.variant != RFC_4122:
        raise ValueError("Source ID 必须是标准 UUID v4。")
    parsed = urlsplit(public_base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("PUBLIC_WEBRTC_BASE_URL 必须是 HTTP(S) 基础地址。")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("PUBLIC_WEBRTC_BASE_URL 不能包含凭据。")
    if parsed.query or parsed.fragment:
        raise ValueError("PUBLIC_WEBRTC_BASE_URL 不能包含 query 或 fragment。")

    path = f"{parsed.path.rstrip('/')}/{source_id}/whep"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
