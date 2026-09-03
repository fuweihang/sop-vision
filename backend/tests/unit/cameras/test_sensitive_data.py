"""Camera 聚合、异常和日志的敏感数据防泄漏测试。"""

import logging

import pytest

from app.modules.cameras.application import (
    CreateCameraCommand,
    CreateCameraSourceCommand,
    UpdateCameraCommand,
    UpdateCameraSourceCommand,
)
from app.modules.cameras.domain import CameraValidationError
from tests.support.cameras.builders import (
    FIXED_TIME,
    CameraBuilder,
    FixedClock,
    uuid4_from_index,
)
from tests.support.cameras.constants import CAMERA_LEAK_SENTINEL


@pytest.mark.sensitive_data
def test_聚合异常和日志不包含密码或完整RTSP地址(caplog: pytest.LogCaptureFixture) -> None:
    sentinel = CAMERA_LEAK_SENTINEL
    builder = CameraBuilder()
    builder.password = sentinel
    camera = builder.build(source_count=1)
    full_url = camera.rtsp_url_for(camera.sources[0].source_id)

    assert full_url == (
        f"rtsp://admin:{CAMERA_LEAK_SENTINEL}@192.168.1.64:554/Streaming/Channels/001"
    )
    assert sentinel not in repr(camera)
    assert full_url not in repr(camera)

    with pytest.raises(CameraValidationError) as caught:
        camera.change_default_preview_source(
            uuid4_from_index(999),
            clock=FixedClock(FIXED_TIME),
        )
    assert sentinel not in str(caught.value)
    assert full_url not in str(caught.value)

    with caplog.at_level(logging.ERROR):
        logging.getLogger("test.camera.domain").error("领域失败：%r", camera)
    assert sentinel not in caplog.text
    assert full_url not in caplog.text


@pytest.mark.sensitive_data
def test_写入命令默认表示不包含密码或Source后缀() -> None:
    """防止框架或异常日志直接格式化应用命令时泄漏 Camera 连接信息。"""

    camera = CameraBuilder().build(source_count=2)
    create_source = CreateCameraSourceCommand(
        name="主码流",
        url_suffix="Streaming/Channels/101",
        is_default_preview=True,
    )
    create_command = CreateCameraCommand(
        name=camera.name,
        ip_address=camera.ip_address,
        rtsp_port=camera.rtsp_port,
        username=camera.credentials.username,
        password=CAMERA_LEAK_SENTINEL,
        sources=(create_source,),
    )
    update_source = UpdateCameraSourceCommand(
        source_id=camera.sources[0].source_id,
        name=camera.sources[0].name,
        url_suffix=camera.sources[0].url_suffix,
        is_default_preview=True,
    )
    update_command = UpdateCameraCommand(
        camera_id=camera.camera_id,
        name=camera.name,
        ip_address=camera.ip_address,
        rtsp_port=camera.rtsp_port,
        username=camera.credentials.username,
        password=CAMERA_LEAK_SENTINEL,
        sources=(update_source,),
    )

    for command, source, suffix in (
        (create_command, create_source, create_source.url_suffix),
        (update_command, update_source, update_source.url_suffix),
    ):
        assert CAMERA_LEAK_SENTINEL not in repr(command)
        assert suffix not in repr(command)
        assert suffix not in repr(source)
