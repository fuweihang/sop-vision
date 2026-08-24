from algorithm.contracts.detection import DetectionMetrics, FrameDetection
from algorithm.demos.viewer.state import DetectionOverlayState


def message(*, run_id: str = "run-1", frame_id: int = 1) -> FrameDetection:
    return FrameDetection(
        task_id="task-1",
        run_id=run_id,
        frame_id=frame_id,
        frame_ts_ms=1000,
        published_at_ms=1001,
        source_width=100,
        source_height=100,
        objects=(),
        metrics=DetectionMetrics(inference_ms=1.0, fps=10.0),
    )


def test_latest_message_replaces_previous_result() -> None:
    state = DetectionOverlayState(expires_after_seconds=2.0)

    assert not state.update(message(frame_id=1), received_at=10.0)
    assert not state.update(message(frame_id=2), received_at=11.0)

    assert state.message is not None
    assert state.message.frame_id == 2


def test_run_change_is_reported_and_new_result_is_kept() -> None:
    state = DetectionOverlayState()
    state.update(message(run_id="old"), received_at=10.0)

    changed = state.update(message(run_id="new"), received_at=11.0)

    assert changed
    assert state.message is not None
    assert state.message.run_id == "new"


def test_message_expires_after_two_seconds() -> None:
    state = DetectionOverlayState(expires_after_seconds=2.0)
    state.update(message(), received_at=10.0)

    assert not state.expire_if_needed(now=12.0)
    assert state.expire_if_needed(now=12.001)
    assert state.message is None
