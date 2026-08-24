"""Camera 领域值规则、确定性端口与敏感值边界测试。"""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.modules.cameras.domain import (
    CameraDomainErrorCode,
    CameraValidationError,
    create_credentials,
    normalize_name,
    normalize_url_suffix,
    validate_ipv4,
    validate_rtsp_port,
)
from app.modules.cameras.domain.testing import FixedClock, FixedIdGenerator
from tests.modules.cameras.builders import uuid4_from_index


def assert_single_error(error: CameraValidationError, field: str, code: str) -> None:
    """以 HTTP 层未来真正消费的字段和稳定 code 断言错误。"""

    assert len(error.errors) == 1
    assert error.errors[0].field == field
    assert error.errors[0].code == code


def test_names_and_url_suffixes_follow_frozen_normalization_rules() -> None:
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
)
def test_invalid_scalar_values_return_stable_field_errors(call, field: str, code: str) -> None:
    with pytest.raises(CameraValidationError) as caught:
        call()
    assert_single_error(caught.value, field, code)


def test_credentials_preserve_whitespace_and_hide_password_from_default_output() -> None:
    credentials = create_credentials(" operator ", " secret with spaces ")

    assert credentials.username == " operator "
    assert credentials.password.reveal() == " secret with spaces "
    assert "secret with spaces" not in repr(credentials)
    assert "secret with spaces" not in repr(credentials.password)
    assert "secret with spaces" not in str(credentials.password)


def test_fixed_id_generator_replays_only_valid_uuid4_values() -> None:
    values = (uuid4_from_index(1), uuid4_from_index(2))
    generator = FixedIdGenerator(values)

    assert generator.new_id() == values[0]
    assert generator.new_id() == values[1]
    with pytest.raises(RuntimeError, match="已经耗尽"):
        generator.new_id()

    invalid_v1 = UUID("00000000-0000-1000-8000-000000000001")
    with pytest.raises(ValueError, match="UUID v4"):
        FixedIdGenerator((invalid_v1,))


def test_fixed_clock_can_advance_deterministically() -> None:
    first = datetime(2026, 8, 24, 8, 0, tzinfo=UTC)
    second = datetime(2026, 8, 24, 8, 5, tzinfo=UTC)
    clock = FixedClock(first)

    assert clock.now() == first
    clock.set(second)
    assert clock.now() == second
