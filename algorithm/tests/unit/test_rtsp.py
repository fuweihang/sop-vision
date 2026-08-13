import time

import numpy as np

from algorithm.common.rtsp import LatestFrameReader


class FakeCapture:
    def __init__(self) -> None:
        self.released = False
        self.read_count = 0

    def isOpened(self) -> bool:  # noqa: N802
        return True

    def read(self):
        time.sleep(0.005)
        self.read_count += 1
        return True, np.full((4, 4, 3), self.read_count % 255, dtype=np.uint8)

    def release(self) -> None:
        self.released = True


def test_reader_returns_newest_frames_and_stops_cleanly() -> None:
    captures: list[FakeCapture] = []

    def factory(_url: str) -> FakeCapture:
        capture = FakeCapture()
        captures.append(capture)
        return capture

    reader = LatestFrameReader(
        "rtsp://user:secret@example.test/stream",
        reconnect_delay_seconds=0.01,
        capture_factory=factory,
    )
    reader.start()
    first = reader.get_latest(timeout=1.0)
    assert first is not None
    second = reader.get_latest(after_sequence=first.sequence, timeout=1.0)
    assert second is not None
    assert second.sequence > first.sequence

    reader.close()

    assert captures[0].released
    assert reader.status().detail == "stopped"
