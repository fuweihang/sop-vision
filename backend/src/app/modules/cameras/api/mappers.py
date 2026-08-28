"""Cameras Application 对象与公开 HTTP Schema 之间的显式映射。"""

from collections.abc import Sequence

from app.modules.cameras.api.schemas import CameraDetail, CameraSourceDetail
from app.modules.cameras.application import CameraRuntimeSummary, summarize_camera_runtime
from app.modules.cameras.domain import Camera
from app.modules.stream_gateway.ports import SourceRuntimeProjection


def camera_detail_from_runtime(
    camera: Camera,
    source_runtime: Sequence[SourceRuntimeProjection],
    runtime_summary: CameraRuntimeSummary,
) -> CameraDetail:
    """把完整 Camera 配置和同批运行投影转换为敏感详情响应。

    映射前重新校验统计，防止未来详情或更新用例把另一批 Source 投影与当前聚合混用。完整
    RTSP URL 只能通过领域方法从当前聚合生成，不能读取 MediaMTX 中可能已经漂移或丢失的
    上游配置。领域方法会按 URI 组件编码，因此响应仍是可直接使用的 Camera 原始源地址。
    """

    projections = tuple(source_runtime)
    expected_summary = summarize_camera_runtime(camera, projections)
    if runtime_summary != expected_summary:
        raise ValueError("Camera 运行状态统计与 Source 投影不一致。")

    sources = tuple(
        CameraSourceDetail(
            source_id=source.source_id,
            name=source.name,
            url_suffix=source.url_suffix,
            rtsp_url=camera.rtsp_url_for(source.source_id),
            is_default_preview=camera.is_default_preview(source.source_id),
            status=projection.status,
            last_checked_at=projection.last_checked_at,
            error=projection.error,
            whep_url=projection.whep_url,
        )
        for source, projection in zip(camera.sources, projections, strict=True)
    )
    return CameraDetail(
        camera_id=camera.camera_id,
        name=camera.name,
        ip_address=camera.ip_address,
        rtsp_port=camera.rtsp_port,
        username=camera.credentials.username,
        password=camera.credentials.password.reveal(),
        default_preview_source_id=camera.default_preview_source_id,
        status=runtime_summary.status,
        online_source_count=runtime_summary.online_source_count,
        source_count=runtime_summary.source_count,
        sources=sources,
        created_at=camera.created_at,
        updated_at=camera.updated_at,
    )
