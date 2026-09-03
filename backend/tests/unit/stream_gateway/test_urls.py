"""MediaMTX RTSP/WHEP URL 构造测试。"""

from ipaddress import IPv4Address
from uuid import UUID

from app.modules.stream_gateway.urls import build_mediamtx_source_url, build_whep_url

SOURCE_ID = UUID("8f14e45f-ea9d-4a7d-9b6d-8c9f0a1b2c3d")


def test_mediamtx_source_url_encodes_reserved_characters_by_component() -> None:
    """凭据、Path 和 query 中的保留字符不能改变 RTSP URL 结构。"""

    result = build_mediamtx_source_url(
        username="operator@:%# name",
        password="secret@:%# word",
        ip_address=IPv4Address("192.0.2.64"),
        rtsp_port=554,
        url_suffix="Streaming Folder/track#1?token=a:b%# c&mode=main stream",
    )

    assert result == (
        "rtsp://operator%40%3A%25%23%20name:secret%40%3A%25%23%20word@192.0.2.64:554/"
        "Streaming%20Folder/track%231?token=a%3Ab%25%23%20c&mode=main%20stream"
    )


def test_whep_url_preserves_public_path_prefix() -> None:
    """反向代理前缀不能因拼接 UUID Path 而丢失。"""

    assert build_whep_url("https://vision.example/media/", SOURCE_ID) == (
        f"https://vision.example/media/{SOURCE_ID}/whep"
    )
