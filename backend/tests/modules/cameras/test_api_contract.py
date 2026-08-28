"""Cameras Schema、占位 Router 与 OpenAPI 的结构契约测试。"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel
from pydantic_core import ValidationError

from app.core.http.problems import PROBLEM_MEDIA_TYPE, ProblemDetails
from app.modules.cameras.api.schemas import (
    CAMERA_ID_EXAMPLE,
    TEST_PASSWORD,
    CameraCreateRequest,
    CameraDetail,
    CameraPage,
    CameraUpdateRequest,
    DefaultPreviewSourceResponse,
    PlaybackInfo,
    SetDefaultPreviewSourceRequest,
)
from scripts.check_camera_placeholders import GateMode, check_camera_placeholders
from scripts.export_openapi import build_openapi_document, export_openapi, serialize_openapi

pytestmark = pytest.mark.anyio

EXPECTED_CAMERA_OPERATIONS = {
    ("/api/v1/cameras", "get"): ("listCameras", {"200", "422", "503"}),
    ("/api/v1/cameras", "post"): ("createCamera", {"201", "422", "503"}),
    ("/api/v1/cameras/{camera_id}", "get"): (
        "getCamera",
        {"200", "404", "422", "500", "503"},
    ),
    ("/api/v1/cameras/{camera_id}", "put"): (
        "updateCamera",
        {"200", "404", "422", "503"},
    ),
    ("/api/v1/cameras/{camera_id}/default-preview-source", "patch"): (
        "setDefaultPreviewSource",
        {"200", "404", "422", "503"},
    ),
    ("/api/v1/cameras/{camera_id}", "delete"): (
        "deleteCamera",
        {"204", "404", "422", "503"},
    ),
    ("/api/v1/camera-sources/{source_id}/playback", "post"): (
        "prepareCameraSourcePlayback",
        {"200", "404", "409", "422", "502", "503"},
    ),
}
SENSITIVE_FIELDS = {"username", "password", "url_suffix", "rtsp_url"}


def _model_example(model: type[BaseModel]) -> dict[str, Any]:
    """读取顶层模型的唯一 example，并在测试内保持严格形状断言。"""

    examples = model.model_json_schema()["examples"]
    assert isinstance(examples, list)
    assert len(examples) == 1
    assert isinstance(examples[0], dict)
    return examples[0]


def _collect_property_names(
    schema: Mapping[str, Any],
    *,
    components: Mapping[str, Any],
    visited_refs: set[str] | None = None,
) -> set[str]:
    """递归解析响应 Schema 的引用，防止敏感字段通过嵌套模型重新进入列表或播放。"""

    visited = visited_refs or set()
    reference = schema.get("$ref")
    if isinstance(reference, str):
        if reference in visited:
            return set()
        visited.add(reference)
        name = reference.rsplit("/", maxsplit=1)[-1]
        return _collect_property_names(
            components[name], components=components, visited_refs=visited
        )

    names = set(schema.get("properties", {}))
    for property_schema in schema.get("properties", {}).values():
        names.update(
            _collect_property_names(
                property_schema,
                components=components,
                visited_refs=visited,
            )
        )
    items = schema.get("items")
    if isinstance(items, Mapping):
        names.update(_collect_property_names(items, components=components, visited_refs=visited))
    for variant_key in ("anyOf", "oneOf", "allOf"):
        for variant in schema.get(variant_key, []):
            names.update(
                _collect_property_names(variant, components=components, visited_refs=visited)
            )
    return names


def test_request_schemas_normalize_fields_and_forbid_unknown_input() -> None:
    """Schema 负责语法规范化和 mass-assignment 防线，聚合规则仍留给领域层。"""

    request = CameraCreateRequest.model_validate(
        {
            "name": "  洗手区 01  ",
            "ip_address": "192.0.2.64",
            "username": " user-with-spaces ",
            "password": " password-with-spaces ",
            "sources": [
                {
                    "name": "  主码流  ",
                    "url_suffix": " ///Streaming/Channels/101 ",
                    "is_default_preview": True,
                }
            ],
        }
    )

    assert request.name == "洗手区 01"
    assert request.rtsp_port == 554
    assert request.username == " user-with-spaces "
    assert request.password == " password-with-spaces "
    assert request.sources[0].name == "主码流"
    assert request.sources[0].url_suffix == "Streaming/Channels/101"

    with pytest.raises(ValidationError, match="extra_forbidden"):
        CameraCreateRequest.model_validate(
            {**_model_example(CameraCreateRequest), "camera_id": CAMERA_ID_EXAMPLE}
        )

    update_without_port = _model_example(CameraUpdateRequest).copy()
    del update_without_port["rtsp_port"]
    with pytest.raises(ValidationError, match="Field required"):
        CameraUpdateRequest.model_validate(update_without_port)


def test_create_sources_keeps_min_items_and_uses_dedicated_empty_error() -> None:
    """运行时空数组 code 不得以移除 OpenAPI 最小条目约束为代价。"""

    sources_schema = CameraCreateRequest.model_json_schema()["properties"]["sources"]
    assert sources_schema["minItems"] == 1

    invalid = _model_example(CameraCreateRequest).copy()
    invalid["sources"] = []
    with pytest.raises(ValidationError) as captured:
        CameraCreateRequest.model_validate(invalid)
    safe_errors = captured.value.errors(include_input=False, include_context=False)
    assert [(error["loc"], error["type"]) for error in safe_errors] == [
        (("sources",), "camera_source_required")
    ]


@pytest.mark.parametrize(
    "model",
    [CameraCreateRequest, CameraUpdateRequest, SetDefaultPreviewSourceRequest],
)
def test_request_examples_are_validated_by_their_schema(model: type[BaseModel]) -> None:
    """生成物中的请求 example 必须可被对应 Pydantic Schema 原样接纳。"""

    model.model_validate(_model_example(model))


@pytest.mark.parametrize(
    "model",
    [CameraDetail, CameraPage, DefaultPreviewSourceResponse, PlaybackInfo],
)
def test_response_examples_are_validated_by_their_schema(model: type[BaseModel]) -> None:
    """响应 example 使用固定 UUID/时间，不能靠手写 JSON 绕过 Schema 漂移。"""

    model.model_validate(_model_example(model))


def test_canonical_source_id_rejects_uppercase_text() -> None:
    """请求体 Source UUID 与路径参数使用同一小写标准文本规则。"""

    with pytest.raises(ValidationError, match="uuid_canonical"):
        SetDefaultPreviewSourceRequest.model_validate({"source_id": CAMERA_ID_EXAMPLE.upper()})


@pytest.mark.sensitive_data
def test_list_and_playback_models_forbid_sensitive_fields_recursively(
    application: FastAPI,
) -> None:
    """黑名单同时检查模型图和固定 example，阻止嵌套响应重新引入连接秘密。"""

    openapi = application.openapi()
    components = openapi["components"]["schemas"]
    for model_name, model in (("CameraPage", CameraPage), ("PlaybackInfo", PlaybackInfo)):
        property_names = _collect_property_names(components[model_name], components=components)
        assert property_names.isdisjoint(SENSITIVE_FIELDS)
        example_text = json.dumps(_model_example(model), ensure_ascii=False)
        assert "rtsp://" not in example_text
        assert TEST_PASSWORD not in example_text


def test_openapi_has_exact_target_paths_operations_responses_and_tags(
    application: FastAPI,
) -> None:
    """七条业务路径只能声明 Foundation 冻结的目标成功与业务错误。"""

    openapi = application.openapi()
    playback_path = openapi["paths"]["/api/v1/camera-sources/{source_id}/playback"]
    # Playback 会收敛 MediaMTX Path，属于有副作用的幂等命令；禁止旧 GET 与 POST 并存，
    # 否则生成客户端和调用方可能继续把它当成安全读取并进行预取或透明重试。
    assert set(playback_path) == {"post"}
    for (path, method), (operation_id, statuses) in EXPECTED_CAMERA_OPERATIONS.items():
        operation = openapi["paths"][path][method]
        assert operation["operationId"] == operation_id
        assert set(operation["responses"]) == statuses
        expected_tag = "camera-sources" if "camera-sources" in path else "cameras"
        assert operation["tags"] == [expected_tag]
        for response in operation["responses"].values():
            assert "X-Trace-Id" in response["headers"]


def test_openapi_uses_problem_media_type_and_required_protocol_headers(
    application: FastAPI,
) -> None:
    """错误媒体类型和缓存/重试 header 必须在生成 Client 前固定下来。"""

    openapi = application.openapi()
    for (path, method), (_, statuses) in EXPECTED_CAMERA_OPERATIONS.items():
        responses = openapi["paths"][path][method]["responses"]
        for status_code in statuses:
            response = responses[status_code]
            if int(status_code) >= 400:
                assert set(response["content"]) == {PROBLEM_MEDIA_TYPE}
                problem_content = response["content"][PROBLEM_MEDIA_TYPE]
                assert problem_content["schema"] == {"$ref": "#/components/schemas/ProblemDetails"}
                assert problem_content["example"]["status"] == int(status_code)
                ProblemDetails.model_validate(problem_content["example"])

    create_headers = openapi["paths"]["/api/v1/cameras"]["post"]["responses"]["201"]["headers"]
    assert {"Location", "Cache-Control"}.issubset(create_headers)
    for method in ("get", "put"):
        detail_headers = openapi["paths"]["/api/v1/cameras/{camera_id}"][method]["responses"][
            "200"
        ]["headers"]
        assert "Cache-Control" in detail_headers
    playback_response = openapi["paths"]["/api/v1/camera-sources/{source_id}/playback"]["post"][
        "responses"
    ]
    retry_headers = playback_response["409"]["headers"]
    assert "Retry-After" in retry_headers
    assert "Cache-Control" in playback_response["200"]["headers"]
    assert (
        "content"
        not in openapi["paths"]["/api/v1/cameras/{camera_id}"]["delete"]["responses"]["204"]
    )


def test_health_operation_ids_and_readiness_problem_are_stable(application: FastAPI) -> None:
    """注册 Cameras 契约不能让既有健康检查的生成客户端符号漂移。"""

    openapi = application.openapi()
    liveness = openapi["paths"]["/api/v1/health/live"]["get"]
    readiness = openapi["paths"]["/api/v1/health/ready"]["get"]
    assert liveness["operationId"] == "healthLiveness"
    assert readiness["operationId"] == "healthReadiness"
    assert set(readiness["responses"]["503"]["content"]) == {PROBLEM_MEDIA_TYPE}


def test_placeholder_handlers_only_raise_not_implemented() -> None:
    """Foundation 只允许纯占位，且不阻止后续切片逐个原位替换完整 handler。"""

    report = check_camera_placeholders(GateMode.FOUNDATION)
    assert not report.invalid_handlers
    assert report.placeholders == (
        "list_cameras",
        "update_camera",
        "set_default_preview_source",
        "delete_camera",
        "prepare_camera_source_playback",
    )


async def test_placeholder_runtime_500_is_not_added_to_target_contract(
    application: FastAPI,
) -> None:
    """占位运行时结果保持脱敏，但不能冒充未来列表接口的正式错误响应。"""

    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/cameras")

    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert response.json()["code"] == "INTERNAL_SERVER_ERROR"
    assert "500" not in application.openapi()["paths"]["/api/v1/cameras"]["get"]["responses"]


def test_problem_example_is_valid_and_openapi_export_is_byte_stable(tmp_path: Path) -> None:
    """导出不进入 lifespan，连续生成及写盘必须得到完全相同的 UTF-8 字节。"""

    schema = build_openapi_document()
    problem_example = schema["paths"]["/api/v1/cameras"]["get"]["responses"]["422"]["content"][
        PROBLEM_MEDIA_TYPE
    ]["example"]
    ProblemDetails.model_validate(problem_example)

    first = serialize_openapi(build_openapi_document())
    second = serialize_openapi(build_openapi_document())
    output_path = tmp_path / "openapi.json"
    written = export_openapi(output_path)
    assert first == second == written == output_path.read_bytes()
    assert written.endswith(b"\n")
