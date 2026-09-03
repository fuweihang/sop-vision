"""Camera 领域值、规范化和敏感值边界测试。"""

from ipaddress import IPv4Address

import pytest

from app.modules.cameras.domain import (
    CameraCredentials,
    CameraDomainErrorCode,
    CameraValidationError,
    SecretValue,
    build_rtsp_url,
    create_credentials,
    normalize_name,
    normalize_url_suffix,
    validate_ipv4,
    validate_rtsp_port,
)


def _assert_single_error(error: CameraValidationError, field: str, code: str) -> None:
    """以 HTTP 层未来真正消费的字段和稳定 code 断言错误。"""

    assert len(error.errors) == 1
    assert error.errors[0].field == field
    assert error.errors[0].code == code


def test_名称和视频源后缀遵守固定的规范化规则() -> None:
    assert normalize_name("  洗手区 01  ") == "洗手区 01"
    assert normalize_url_suffix("  ///ABC/path?profile=1/  ") == "ABC/path?profile=1/"
    # 比较大小写敏感，因此规范化函数本身绝不能 lower/casefold。
    assert normalize_url_suffix("ABC") != normalize_url_suffix("abc")


@pytest.mark.parametrize(
    ("call", "field", "code"),
    [
        (lambda: normalize_name(" \t "), "name", CameraDomainErrorCode.REQUIRED),
        (
            lambda: normalize_name("x" * 129),
            "name",
            CameraDomainErrorCode.STRING_TOO_LONG,
        ),
        (
            lambda: validate_ipv4("2001:db8::1"),
            "ip_address",
            CameraDomainErrorCode.INVALID_IP_ADDRESS,
        ),
        (
            lambda: validate_ipv4("192.168.001.10"),
            "ip_address",
            CameraDomainErrorCode.INVALID_IP_ADDRESS,
        ),
        (lambda: validate_rtsp_port(0), "rtsp_port", CameraDomainErrorCode.OUT_OF_RANGE),
        (lambda: validate_rtsp_port(65536), "rtsp_port", CameraDomainErrorCode.OUT_OF_RANGE),
        (lambda: validate_rtsp_port(True), "rtsp_port", CameraDomainErrorCode.OUT_OF_RANGE),
        (
            lambda: normalize_url_suffix(" /// "),
            "url_suffix",
            CameraDomainErrorCode.REQUIRED,
        ),
        (
            lambda: normalize_url_suffix("x" * 1025),
            "url_suffix",
            CameraDomainErrorCode.STRING_TOO_LONG,
        ),
        (
            lambda: create_credentials("x" * 129, "secret"),
            "username",
            CameraDomainErrorCode.STRING_TOO_LONG,
        ),
        (
            lambda: create_credentials("admin", "x" * 513),
            "password",
            CameraDomainErrorCode.STRING_TOO_LONG,
        ),
    ],
    ids=[
        "名称不能为空",
        "名称长度上限",
        "拒绝IPv6",
        "拒绝带前导零的IPv4",
        "端口下界",
        "端口上界",
        "拒绝布尔端口",
        "视频源后缀不能为空",
        "视频源后缀长度上限",
        "用户名长度上限",
        "密码长度上限",
    ],
)
def test_无效标量返回稳定的字段错误(call, field: str, code: str) -> None:
    with pytest.raises(CameraValidationError) as caught:
        call()
    _assert_single_error(caught.value, field, code)


def test_凭据保留空白且默认输出隐藏密码() -> None:
    credentials = create_credentials(" operator ", " secret with spaces ")

    assert credentials.username == " operator "
    assert credentials.password.reveal() == " secret with spaces "
    assert "secret with spaces" not in repr(credentials)
    assert "secret with spaces" not in repr(credentials.password)
    assert "secret with spaces" not in str(credentials.password)


def test_RTSP地址按组件编码凭据路径和查询参数() -> None:
    """保留 Source 路径和 query 结构，同时避免保留字符改变 URL 含义。"""

    result = build_rtsp_url(
        credentials=CameraCredentials(
            username="operator@:%# name",
            password=SecretValue("secret@:%# word"),
        ),
        camera_ip=IPv4Address("192.168.1.64"),
        rtsp_port=554,
        url_suffix="Streaming Folder/track#1?token=a:b%# c&mode=main stream&enabled",
    )

    assert result == (
        "rtsp://operator%40%3A%25%23%20name:secret%40%3A%25%23%20word@192.168.1.64:554/"
        "Streaming%20Folder/track%231?token=a%3Ab%25%23%20c&mode=main%20stream&enabled"
    )
