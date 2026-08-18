from algorithm.common.config import redact_url


def test_redact_url_hides_rtsp_credentials() -> None:
    value = "rtsp://admin:secret%23@192.168.1.10:554/stream"

    assert redact_url(value) == "rtsp://***:***@192.168.1.10:554/stream"
