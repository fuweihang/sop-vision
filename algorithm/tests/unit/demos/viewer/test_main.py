import pytest

from algorithm.demos.viewer.__main__ import build_parser


def test_viewer_cli_uses_task_configuration_for_preview_addresses() -> None:
    args = build_parser().parse_args([])

    assert not hasattr(args, "rtsp_url")
    assert not hasattr(args, "redis_url")


@pytest.mark.parametrize("option", ["--rtsp-url", "--redis-url"])
def test_removed_preview_address_options_are_rejected(option: str) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([option, "unused"])
