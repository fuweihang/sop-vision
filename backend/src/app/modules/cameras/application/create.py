"""创建 Camera 聚合并在提交后尽力同步媒体运行态。"""

import asyncio
from dataclasses import dataclass, field
from ipaddress import IPv4Address

from app.modules.cameras.application.media import build_camera_desired_sources
from app.modules.cameras.application.ports import CameraUnitOfWork
from app.modules.cameras.application.status import CameraRuntimeSummary, summarize_camera_runtime
from app.modules.cameras.domain import Camera, Clock, IdGenerator, NewCameraSource
from app.modules.stream_gateway.ports import (
    SourceRuntimeProjection,
    StreamGatewayInvalidResponseError,
    StreamGatewayPort,
    StreamGatewayUnavailableError,
)
from app.modules.stream_gateway.projection import project_source_runtime


@dataclass(frozen=True, slots=True, repr=False)
class CreateCameraSourceCommand:
    """创建命令中的一路 Source；不包含由服务端生成的 ID。"""

    name: str
    url_suffix: str
    is_default_preview: bool = False


@dataclass(frozen=True, slots=True, repr=False)
class CreateCameraCommand:
    """框架无关的 Camera 创建输入。

    ``repr`` 被关闭是因为对象同时包含密码和 Source 后缀；即使未来异常日志误打印命令，默认
    表示也不会把请求内容带入日志。
    """

    name: str
    ip_address: str | IPv4Address
    rtsp_port: int
    username: str
    password: str = field(repr=False)
    sources: tuple[CreateCameraSourceCommand, ...]


@dataclass(frozen=True, slots=True, repr=False)
class CreateCameraResult:
    """创建用例的有类型输出；API 层负责转换为公开响应 Schema。"""

    camera: Camera
    source_runtime: tuple[SourceRuntimeProjection, ...]
    runtime_summary: CameraRuntimeSummary


async def create_camera(
    command: CreateCameraCommand,
    *,
    uow: CameraUnitOfWork,
    stream_gateway: StreamGatewayPort,
    id_generator: IdGenerator,
    clock: Clock,
) -> CreateCameraResult:
    """创建完整聚合，提交后尽力同步 MediaMTX 并返回一次运行态观察。

    数据库事务只覆盖聚合写入。提交成功后发生的媒体错误不能反向删除或回滚配置；后台对账会
    继续恢复 Path。只捕获 Port 声明的两类脱敏媒体错误，任务取消和程序缺陷继续向上传播。
    """

    camera = Camera.create(
        name=command.name,
        ip_address=command.ip_address,
        rtsp_port=command.rtsp_port,
        username=command.username,
        password=command.password,
        sources=tuple(
            NewCameraSource(
                name=source.name,
                url_suffix=source.url_suffix,
                is_default_preview=source.is_default_preview,
            )
            for source in command.sources
        ),
        id_generator=id_generator,
        clock=clock,
    )

    try:
        await uow.cameras.add(camera)
        await uow.commit()
    except asyncio.CancelledError:
        # 取消必须优先传播。即使清理本身遇到普通数据库错误，也不能把请求取消改写成业务 503；
        # 请求级 Session 依赖仍会在退出时执行最后一道防御性回滚和关闭。
        try:
            await uow.rollback()
        except Exception:
            pass
        raise
    except Exception:
        # Fake 和未来其他 UoW 不一定像当前 SQLAlchemy 实现一样在失败内部自动回滚。用例在
        # 提交边界再做一次显式回滚，保证异常路径不会把未完成事务留给请求级 Session。
        await uow.rollback()
        raise

    for desired_source in build_camera_desired_sources(camera):
        try:
            await stream_gateway.ensure_path(desired_source)
        except (StreamGatewayUnavailableError, StreamGatewayInvalidResponseError):
            # 单路失败不阻塞其余 Source，也不在这里记录异常或 DesiredSource；Adapter 已负责
            # 脱敏 I/O 日志，后台对账会在后续轮次重试当前数据库事实。
            continue

    failed_at = None
    try:
        observation = await stream_gateway.fetch_runtime_path_snapshot()
    except (StreamGatewayUnavailableError, StreamGatewayInvalidResponseError) as error:
        observation = error
        # 失败投影需要同一次完成时间。Clock 由调用方注入，使全部 Source 共享确定且可测的
        # UTC 时刻；成功快照则直接使用 Adapter 在完成全部分页后记录的 checked_at。
        failed_at = clock.now()

    source_runtime = project_source_runtime(
        tuple(source.source_id for source in camera.sources),
        observation,
        failed_at=failed_at,
        whep_url_for=stream_gateway.whep_url_for,
    )
    runtime_summary = summarize_camera_runtime(camera, source_runtime)
    return CreateCameraResult(
        camera=camera,
        source_runtime=source_runtime,
        runtime_summary=runtime_summary,
    )
