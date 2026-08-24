"""在 Camera/Source 业务对象和 SQLAlchemy ORM 记录之间复制数据。

Camera/Source 业务对象不知道数据库列，ORM 记录也不会直接返回给应用服务。把转换集中在
本文件可以清楚控制哪些字段会写入或读出，尤其能看清密码只在哪些位置被显式取出。
"""

from collections.abc import Sequence

from app.modules.cameras.domain import Camera, CameraSource
from app.modules.cameras.persistence.models import CameraRow, CameraSourceRow


def camera_to_rows(camera: Camera) -> tuple[CameraRow, tuple[CameraSourceRow, ...]]:
    """把一个新 Camera 及其全部 Source 转成待插入数据库的 ORM 记录。

    此函数只做字段复制，不重新修剪名称、生成 ID 或修改 Source 顺序；这些规则已经由
    Camera 对象保证。密码在 Camera 对象中被包装为不可直接打印的值，只在填写数据库
    ``password`` 列时调用 ``reveal``。
    """

    camera_row = CameraRow(
        camera_id=camera.camera_id,
        name=camera.name,
        ip_address=camera.ip_address,
        rtsp_port=camera.rtsp_port,
        username=camera.credentials.username,
        password=camera.credentials.password.reveal(),
        default_preview_source_id=camera.default_preview_source_id,
        created_at=camera.created_at,
        updated_at=camera.updated_at,
    )
    return camera_row, tuple(source_to_row(source) for source in camera.sources)


def source_to_row(source: CameraSource) -> CameraSourceRow:
    """把一路新 Source 转成 ORM 记录，不在这里重复业务规则检查或修改字段。"""

    return CameraSourceRow(
        source_id=source.source_id,
        camera_id=source.camera_id,
        name=source.name,
        url_suffix=source.url_suffix,
        sort_order=source.sort_order,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


def rows_to_camera(camera_row: CameraRow, source_rows: Sequence[CameraSourceRow]) -> Camera:
    """用一条 Camera 记录和它的全部 Source 记录重建 Camera 业务对象。

    Repository 必须提前把所有 Source 按 ``sort_order`` 排好并传入。这里不会补齐缺失 Source、
    修复错误顺序或替换默认 Source；``reconstitute`` 会检查这些数据，发现损坏就明确报错，
    从而避免应用层拿到一个看似正常但内容不完整的 Camera。
    """

    sources = tuple(
        CameraSource.reconstitute(
            source_id=row.source_id,
            camera_id=row.camera_id,
            name=row.name,
            url_suffix=row.url_suffix,
            sort_order=row.sort_order,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in source_rows
    )
    return Camera.reconstitute(
        camera_id=camera_row.camera_id,
        name=camera_row.name,
        ip_address=camera_row.ip_address,
        rtsp_port=camera_row.rtsp_port,
        username=camera_row.username,
        # ORM 记录中的密码只交给 Camera 对象重新包装，不写日志，也不拼进任何异常消息。
        password=camera_row.password,
        default_preview_source_id=camera_row.default_preview_source_id,
        sources=sources,
        created_at=camera_row.created_at,
        updated_at=camera_row.updated_at,
    )


def update_camera_row(row: CameraRow, camera: Camera) -> None:
    """把 Camera 当前配置复制到已加锁的 ORM 记录。

    ``camera_id`` 和 ``created_at`` 代表数据库中原对象的身份与创建时间，更新时不能被调用方
    覆盖，所以这里只修改允许变化的配置和 ``updated_at``。
    """

    row.name = camera.name
    row.ip_address = camera.ip_address
    row.rtsp_port = camera.rtsp_port
    row.username = camera.credentials.username
    row.password = camera.credentials.password.reveal()
    row.default_preview_source_id = camera.default_preview_source_id
    row.updated_at = camera.updated_at


def update_source_row(row: CameraSourceRow, source: CameraSource) -> None:
    """更新一条被保留的 Source 记录。

    Source ID、所属 Camera 和创建时间以数据库中的原记录为准，不能随着一次 Camera 配置
    更新而改变；名称、URL 后缀、顺序和更新时间则来自新的完整 Camera 配置。
    """

    row.name = source.name
    row.url_suffix = source.url_suffix
    row.sort_order = source.sort_order
    row.updated_at = source.updated_at
