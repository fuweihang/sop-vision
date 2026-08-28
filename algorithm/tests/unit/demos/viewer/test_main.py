import pytest

from algorithm.demos.viewer.__main__ import build_parser


def test_viewer_cli_uses_task_configuration_for_preview_addresses() -> None:
    args = build_parser().parse_args([])

    assert args.task_id == "detector-001"
    assert args.task_id_2 == "detector-002"
    assert not hasattr(args, "rtsp_url")
    assert not hasattr(args, "redis_url")


def test_viewer_cli_accepts_two_task_ids() -> None:
    args = build_parser().parse_args(
        ["--task-id", "camera-task-1", "--task-id-2", "camera-task-2"]
    )

    assert args.task_id == "camera-task-1"
    assert args.task_id_2 == "camera-task-2"


@pytest.mark.parametrize("option", ["--rtsp-url", "--redis-url"])
def test_removed_preview_address_options_are_rejected(option: str) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([option, "unused"])
