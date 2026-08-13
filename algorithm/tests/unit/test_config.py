from algorithm.common.config import DetectorConfig, redact_url


def test_redact_url_hides_rtsp_credentials() -> None:
    value = "rtsp://admin:secret%23@192.168.1.10:554/stream"

    assert redact_url(value) == "rtsp://***:***@192.168.1.10:554/stream"


def test_environment_task_id_derives_roi_channel(monkeypatch) -> None:
    monkeypatch.setenv("DETECTOR_TASK_ID", "camera-7-person")

    config = DetectorConfig.from_environment()

    assert config.task_id == "camera-7-person"
    assert config.roi_channel == "vision:config:roi:camera-7-person"


def test_explicit_environment_channel_wins(monkeypatch) -> None:
    monkeypatch.setenv("DETECTOR_TASK_ID", "camera-7-person")
    monkeypatch.setenv("DETECTOR_ROI_CHANNEL", "custom:roi")

    assert DetectorConfig.from_environment().roi_channel == "custom:roi"


def test_gpu_zero_is_the_default_device(monkeypatch) -> None:
    monkeypatch.delenv("DETECTOR_DEVICE", raising=False)

    assert DetectorConfig.from_environment().device == "0"


def test_environment_can_request_automatic_device_selection(monkeypatch) -> None:
    monkeypatch.setenv("DETECTOR_DEVICE", "AUTO")

    assert DetectorConfig.from_environment().device is None
