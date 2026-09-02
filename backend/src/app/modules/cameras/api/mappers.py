"""Cameras Application 对象与公开 HTTP Schema 之间的显式映射。"""

from collections.abc import Sequence

from app.modules.cameras.api.schemas import (
    CameraDetail,
    CameraPage,
    CameraSourceDetail,
    CameraSummary,
    DefaultPreviewSourceResponse,
    DefaultPreviewSourceSummary,
)
from app.modules.cameras.application import (
    CameraListItemResult,
    CameraListResult,
    CameraRuntimeSummary,
    SetDefaultPreviewSourceResult,
    summarize_camera_runtime,
)
from app.modules.cameras.domain import Camera
from app.modules.stream_gateway.ports import SourceRuntimeProjection


def default_preview_source_from_result(
    result: SetDefaultPreviewSourceResult,
) -> DefaultPreviewSourceResponse:
    """白名单映射默认源写结果，避免完整 Camera 聚合进入非敏感响应。"""

    return DefaultPreviewSourceResponse(
        camera_id=result.camera_id,
        default_preview_source_id=result.default_preview_source_id,
        updated_at=result.updated_at,
    )


def camera_page_from_result(result: CameraListResult) -> CameraPage:
    """把列表 Application 结果转换为严格非敏感的分页响应。

    分页元数据直接来自已验证的应用结果；每条摘要必须经由专用逐字段 Mapper，不能把包含凭据和
    Source 后缀的 Camera 聚合展开成字典后再删字段。白名单构造可以让领域未来新增字段时保持默认
    不公开。
    """

    return CameraPage(
        items=[camera_summary_from_runtime(item) for item in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


def camera_summary_from_runtime(item: CameraListItemResult) -> CameraSummary:
    """逐字段构造一条列表摘要，并验证默认 Source 与运行态投影来自同一聚合。"""

    camera = item.camera
    projections = tuple(item.source_runtime)
    expected_summary = summarize_camera_runtime(camera, projections)
    if item.runtime_summary != expected_summary:
        raise ValueError("Camera 列表运行状态统计与 Source 投影不一致。")

    default_source = next(
        source for source in camera.sources if source.source_id == camera.default_preview_source_id
    )
    projections_by_id = {projection.source_id: projection for projection in projections}
    default_runtime = projections_by_id.get(default_source.source_id)
    if default_runtime is None or len(projections_by_id) != len(projections):
        # summarize_camera_runtime 已核对 ID 和顺序；保留防御分支，避免未来 Mapper 调整后静默返回
        # 另一路 Source 的状态或在重复 ID 时发生字典覆盖。
        raise ValueError("Camera 列表默认 Source 缺少唯一运行状态投影。")

    return CameraSummary(
        camera_id=camera.camera_id,
        name=camera.name,
        ip_address=camera.ip_address,
        rtsp_port=camera.rtsp_port,
        status=item.runtime_summary.status,
        online_source_count=item.runtime_summary.online_source_count,
        source_count=item.runtime_summary.source_count,
        default_preview_source=DefaultPreviewSourceSummary(
            source_id=default_source.source_id,
            name=default_source.name,
            status=default_runtime.status,
            last_checked_at=default_runtime.last_checked_at,
            whep_url=default_runtime.whep_url,
        ),
        created_at=camera.created_at,
        updated_at=camera.updated_at,
    )


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
