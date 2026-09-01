"""Cameras Router 与完整目标 OpenAPI 契约。

创建和详情 handler 已实现；其余四个 handler 在对应切片落地前继续保持纯
``raise NotImplementedError``。全部路径预先注册到真实应用，使 OpenAPI、前端生成类型和 MSW
共享同一棵路由树；剩余占位的临时 500 不属于声明契约。
"""

from typing import Any

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app.core.http import (
    CanonicalUUID4,
    no_content_response,
    problem_responses,
    success_response,
)
from app.modules.cameras.api.dependencies import (
    CameraClockDependency,
    CameraIdGeneratorDependency,
    CameraListParametersDependency,
    CameraUnitOfWorkDependency,
)
from app.modules.cameras.api.mappers import camera_detail_from_runtime, camera_page_from_result
from app.modules.cameras.api.schemas import (
    CameraCreateRequest,
    CameraDetail,
    CameraPage,
    CameraUpdateRequest,
    DefaultPreviewSourceResponse,
    SetDefaultPreviewSourceRequest,
)
from app.modules.cameras.application import (
    CreateCameraCommand,
    CreateCameraSourceCommand,
)
from app.modules.cameras.application import create_camera as execute_create_camera
from app.modules.cameras.application import get_camera_detail as execute_get_camera_detail
from app.modules.cameras.application import list_cameras as execute_list_cameras
from app.modules.stream_gateway.api.dependencies import StreamGatewayDependency

router = APIRouter()


def _example(model: type[BaseModel]) -> dict[str, Any]:
    """读取已由 Pydantic Schema 持有的唯一固定 example，避免 Router 再维护一份副本。"""

    examples = model.model_json_schema().get("examples")
    if not isinstance(examples, list) or len(examples) != 1 or not isinstance(examples[0], dict):
        raise RuntimeError(f"{model.__name__} 必须定义且只能定义一个顶层 OpenAPI example。")
    return examples[0]


@router.get(
    "/cameras",
    operation_id="listCameras",
    tags=["cameras"],
    response_model=CameraPage,
    responses={
        status.HTTP_200_OK: success_response(
            "返回一页 Camera 摘要。", example=_example(CameraPage)
        ),
        **problem_responses(
            [
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ]
        ),
    },
)
async def list_cameras(
    parameters: CameraListParametersDependency,
    uow: CameraUnitOfWorkDependency,
    stream_gateway: StreamGatewayDependency,
    clock: CameraClockDependency,
) -> CameraPage:
    """返回一页非敏感 Camera 摘要；外部媒体故障只降级运行状态。"""

    result = await execute_list_cameras(
        parameters.criteria,
        parameters.page,
        parameters.page_size,
        uow=uow,
        stream_gateway=stream_gateway,
        clock=clock,
    )
    return camera_page_from_result(result)


@router.post(
    "/cameras",
    operation_id="createCamera",
    tags=["cameras"],
    response_model=CameraDetail,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: success_response(
            "Camera 聚合创建成功。",
            example=_example(CameraDetail),
            location=True,
            no_store=True,
        ),
        **problem_responses(
            [status.HTTP_422_UNPROCESSABLE_CONTENT, status.HTTP_503_SERVICE_UNAVAILABLE]
        ),
    },
)
async def create_camera(
    request: CameraCreateRequest,
    response: Response,
    uow: CameraUnitOfWorkDependency,
    stream_gateway: StreamGatewayDependency,
    id_generator: CameraIdGeneratorDependency,
    clock: CameraClockDependency,
) -> CameraDetail:
    # 创建完整 Camera 聚合；数据库提交后的媒体同步失败只影响本次运行状态投影，不能把已经
    # 持久化成功的配置伪装成创建失败。
    result = await execute_create_camera(
        CreateCameraCommand(
            name=request.name,
            ip_address=request.ip_address,
            rtsp_port=request.rtsp_port,
            username=request.username,
            password=request.password,
            sources=tuple(
                CreateCameraSourceCommand(
                    name=source.name,
                    url_suffix=source.url_suffix,
                    is_default_preview=source.is_default_preview,
                )
                for source in request.sources
            ),
        ),
        uow=uow,
        stream_gateway=stream_gateway,
        id_generator=id_generator,
        clock=clock,
    )
    # FastAPI 会把临时 Response 上的 header 复制到 response_model 校验后的最终 JSON 响应。
    # Location 使用相对 API 路径，no-store 则保护本接口按产品契约返回的凭据和完整 RTSP URL。
    response.headers["Location"] = f"/api/v1/cameras/{result.camera.camera_id}"
    response.headers["Cache-Control"] = "no-store"
    return camera_detail_from_runtime(
        result.camera,
        result.source_runtime,
        result.runtime_summary,
    )


@router.get(
    "/cameras/{camera_id}",
    operation_id="getCamera",
    tags=["cameras"],
    response_model=CameraDetail,
    responses={
        status.HTTP_200_OK: success_response(
            "返回 Camera 完整配置与状态投影。",
            example=_example(CameraDetail),
            no_store=True,
        ),
        **problem_responses(
            [
                status.HTTP_404_NOT_FOUND,
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ]
        ),
    },
)
async def get_camera(
    camera_id: CanonicalUUID4,
    response: Response,
    uow: CameraUnitOfWorkDependency,
    stream_gateway: StreamGatewayDependency,
    clock: CameraClockDependency,
) -> CameraDetail:
    result = await execute_get_camera_detail(
        camera_id,
        uow=uow,
        stream_gateway=stream_gateway,
        clock=clock,
    )
    # CameraDetail 包含密码和完整 RTSP URL，即使客户端或代理有默认缓存策略也必须禁止保存。
    response.headers["Cache-Control"] = "no-store"
    return camera_detail_from_runtime(
        result.camera,
        result.source_runtime,
        result.runtime_summary,
    )


@router.put(
    "/cameras/{camera_id}",
    operation_id="updateCamera",
    tags=["cameras"],
    response_model=CameraDetail,
    responses={
        status.HTTP_200_OK: success_response(
            "Camera 完整配置更新成功。",
            example=_example(CameraDetail),
            no_store=True,
        ),
        **problem_responses(
            [
                status.HTTP_404_NOT_FOUND,
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ]
        ),
    },
)
async def update_camera(camera_id: CanonicalUUID4, _request: CameraUpdateRequest) -> CameraDetail:
    raise NotImplementedError


@router.patch(
    "/cameras/{camera_id}/default-preview-source",
    operation_id="setDefaultPreviewSource",
    tags=["cameras"],
    response_model=DefaultPreviewSourceResponse,
    responses={
        status.HTTP_200_OK: success_response(
            "默认预览 Source 切换成功。",
            example=_example(DefaultPreviewSourceResponse),
        ),
        **problem_responses(
            [
                status.HTTP_404_NOT_FOUND,
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ]
        ),
    },
)
async def set_default_preview_source(
    camera_id: CanonicalUUID4,
    _request: SetDefaultPreviewSourceRequest,
) -> DefaultPreviewSourceResponse:
    raise NotImplementedError


@router.delete(
    "/cameras/{camera_id}",
    operation_id="deleteCamera",
    tags=["cameras"],
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    responses={
        status.HTTP_204_NO_CONTENT: no_content_response("Camera 聚合删除成功，不返回响应体。"),
        **problem_responses(
            [
                status.HTTP_404_NOT_FOUND,
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ]
        ),
    },
)
async def delete_camera(camera_id: CanonicalUUID4) -> None:
    raise NotImplementedError
