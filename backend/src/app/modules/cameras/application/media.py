"""从 Camera 聚合派生 MediaMTX Desired State 的共享纯函数。"""

from app.modules.cameras.domain import Camera, CameraSource
from app.modules.stream_gateway.ports import DesiredSource
from app.modules.stream_gateway.urls import build_mediamtx_source_url


def build_desired_source(camera: Camera, source: CameraSource) -> DesiredSource:
    """为当前 Camera 的一路 Source 构造带安全编码的媒体期望状态。

    Args:
        camera: 提供设备地址、端口和 RTSP 凭据的完整聚合。
        source: 必须属于该 Camera 的一路 Source。

    Returns:
        可直接交给 ``StreamGatewayPort.ensure_path`` 的不可变对象。

    Raises:
        ValueError: Source 不属于传入 Camera，或聚合字段无法构造合法 RTSP URL。

    归属检查不能省略。创建、更新和后台对账都会复用此函数；若误把另一个
    Camera 的 Source 与当前凭据拼接，会把错误地址写入同名 MediaMTX Path。
    """

    if source.camera_id != camera.camera_id or source not in camera.sources:
        raise ValueError("只能为当前 Camera 拥有的 Source 构造媒体期望状态。")

    # 明文密码只在这里短暂交给统一 URL 构造器完成百分号编码；返回类型会隐藏 URL 的默认
    # repr，调用方也不应把 DesiredSource 或 source_url 写入日志、异常和持久化缓存。
    return DesiredSource(
        source_id=source.source_id,
        source_url=build_mediamtx_source_url(
            username=camera.credentials.username,
            password=camera.credentials.password.reveal(),
            ip_address=camera.ip_address,
            rtsp_port=camera.rtsp_port,
            url_suffix=source.url_suffix,
        ),
    )


def build_camera_desired_sources(camera: Camera) -> tuple[DesiredSource, ...]:
    """按 Camera 内的固定 Source 顺序构造全部媒体期望状态。"""

    return tuple(build_desired_source(camera, source) for source in camera.sources)
