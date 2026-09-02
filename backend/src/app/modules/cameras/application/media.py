"""从 Camera 聚合派生 MediaMTX Desired State，并计算完整更新需要的媒体差异。"""

from dataclasses import dataclass
from uuid import UUID

from app.modules.cameras.domain import Camera, CameraSource
from app.modules.stream_gateway.ports import DesiredSource
from app.modules.stream_gateway.urls import build_mediamtx_source_url


@dataclass(frozen=True, slots=True, repr=False)
class CameraMediaDiff:
    """一次 Camera 更新提交后需要执行的最小 MediaMTX 操作。

    ``ensure_sources`` 保存新聚合中的完整 Desired State，顺序与新 Source 数组一致；
    ``release_source_ids`` 保存旧聚合中已经删除的 Source ID，顺序与旧数组一致。关闭默认
    ``repr`` 是为了避免未来给 ``DesiredSource`` 增加字段时意外打印带凭据的上游地址。
    """

    ensure_sources: tuple[DesiredSource, ...]
    release_source_ids: tuple[UUID, ...]


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


def diff_camera_desired_sources(before: Camera, after: Camera) -> CameraMediaDiff:
    """比较同一 Camera 更新前后的 Desired State，返回最小媒体操作。

    Source 名称、默认标记和展示顺序不进入 ``DesiredSource``，因此只改这些字段不会重载
    MediaMTX Path。连接字段或某路后缀变化会改变完整上游 URL，从而确保对应 Path；新增和
    删除则分别进入 ensure/release。该函数只计算不可变值，不执行 I/O，也不读取数据库。

    Raises:
        ValueError: 两个聚合不是同一 Camera，或聚合内部出现重复 Source ID。合法领域对象
            不会命中这些分支；保留检查是为了避免字典覆盖后静默生成错误差异。
    """

    if before.camera_id != after.camera_id:
        raise ValueError("只能比较同一 Camera 更新前后的媒体状态。")

    previous = build_camera_desired_sources(before)
    current = build_camera_desired_sources(after)
    previous_by_id = {item.source_id: item for item in previous}
    current_ids = {item.source_id for item in current}
    if len(previous_by_id) != len(previous) or len(current_ids) != len(current):
        raise ValueError("Camera 媒体差异不能包含重复 Source ID。")

    return CameraMediaDiff(
        ensure_sources=tuple(
            item for item in current if previous_by_id.get(item.source_id) != item
        ),
        release_source_ids=tuple(
            item.source_id for item in previous if item.source_id not in current_ids
        ),
    )
