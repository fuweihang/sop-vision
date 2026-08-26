"""Cameras Foundation 占位 Router 与完整目标 OpenAPI 契约。

七个 handler 在各功能切片实现前故意只有 ``raise NotImplementedError``。路径先注册到真实
应用，使 OpenAPI、前端生成类型和 MSW 可以并行演进；占位运行时的临时 500 不属于声明契约。
"""

from typing import Any

from fastapi import APIRouter, status
from pydantic import BaseModel

from app.core.http import (
    CanonicalUUID4,
    no_content_response,
    problem_responses,
    success_response,
)
from app.modules.cameras.api.dependencies import CameraListParametersDependency
from app.modules.cameras.api.schemas import (
    CameraCreateRequest,
    CameraDetail,
    CameraPage,
    CameraUpdateRequest,
    DefaultPreviewSourceResponse,
    PlaybackInfo,
    SetDefaultPreviewSourceRequest,
)

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
            [status.HTTP_422_UNPROCESSABLE_CONTENT, status.HTTP_503_SERVICE_UNAVAILABLE]
        ),
    },
)
async def list_cameras(_parameters: CameraListParametersDependency) -> CameraPage:
    raise NotImplementedError


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
async def create_camera(_request: CameraCreateRequest) -> CameraDetail:
    raise NotImplementedError


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
async def get_camera(camera_id: CanonicalUUID4) -> CameraDetail:
    raise NotImplementedError


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


@router.post(
    "/camera-sources/{source_id}/playback",
    operation_id="prepareCameraSourcePlayback",
    tags=["camera-sources"],
    response_model=PlaybackInfo,
    responses={
        status.HTTP_200_OK: success_response(
            "准备或恢复 Source 映射，并返回已就绪的 WHEP 播放地址。",
            example=_example(PlaybackInfo),
            no_store=True,
        ),
        **problem_responses(
            [
                status.HTTP_404_NOT_FOUND,
                status.HTTP_409_CONFLICT,
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                status.HTTP_502_BAD_GATEWAY,
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ],
            retry_after_statuses=[status.HTTP_409_CONFLICT],
        ),
    },
)
async def prepare_camera_source_playback(source_id: CanonicalUUID4) -> PlaybackInfo:
    raise NotImplementedError
