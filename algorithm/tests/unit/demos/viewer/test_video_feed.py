import time

import numpy as np

from algorithm.demos.viewer.video_feed import RtspVideoFeed


class FakeCapture:
    def __init__(self) -> None:
        self.released = False

    def isOpened(self) -> bool:  # noqa: N802
        return True

    def read(self):
        time.sleep(0.005)
        frame = np.zeros((2, 2, 3), dtype=np.uint8)
        frame[:, :] = (10, 20, 30)
        return True, frame

    def release(self) -> None:
        self.released = True


def test_video_feed_converts_bgr_to_copied_rgb_and_closes() -> None:
    capture = FakeCapture()
    feed = RtspVideoFeed(
        "rtsp://camera/stream",
        reconnect_delay_seconds=0.01,
        capture_factory=lambda _url: capture,
    )

    feed.start()
    deadline = time.monotonic() + 1.0
    frame = None
    while frame is None and time.monotonic() < deadline:
        frame = feed.get_latest()
        time.sleep(0.01)
    feed.close()

    assert frame is not None
    assert frame.pixels[0, 0].tolist() == [30, 20, 10]
    assert frame.pixels.flags["OWNDATA"]
    assert capture.released


class BrokenCapture(FakeCapture):
    def read(self):
        return False, None


def test_video_feed_reconnects_after_read_failure() -> None:
    broken = BrokenCapture()
    healthy = FakeCapture()
    captures = iter((broken, healthy))
    feed = RtspVideoFeed(
        "rtsp://camera/stream",
        reconnect_delay_seconds=0.01,
        capture_factory=lambda _url: next(captures),
    )

    feed.start()
    deadline = time.monotonic() + 1.0
    frame = None
    while frame is None and time.monotonic() < deadline:
        frame = feed.get_latest()
        time.sleep(0.01)
    feed.close()

    assert frame is not None
    assert broken.released
    assert healthy.released
