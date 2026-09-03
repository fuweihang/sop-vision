"""Cameras 公共请求与响应 Schema 的兼容性测试。"""

import json
from collections.abc import Mapping
from typing import Any

import pytest
from fastapi import FastAPI
from pydantic import BaseModel
from pydantic_core import ValidationError

from app.modules.cameras.api.schemas import (
    CAMERA_ID_EXAMPLE,
    TEST_PASSWORD,
    CameraCreateRequest,
    CameraDetail,
    CameraPage,
    CameraUpdateRequest,
    DefaultPreviewSourceResponse,
    SetDefaultPreviewSourceRequest,
)

SENSITIVE_FIELDS = {"username", "password", "url_suffix", "rtsp_url"}


def _model_example(model: type[BaseModel]) -> dict[str, Any]:
    """读取顶层模型的唯一 example，避免测试和生成 OpenAPI 使用不同样例。"""

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
    """递归解析响应 Schema 引用，防止秘密字段从嵌套模型重新进入列表。"""

    visited = visited_refs or set()
    reference = schema.get("$ref")
    if isinstance(reference, str):
        # 循环引用只需检查一次；继续递归会无限循环，也不会发现新的字段。
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


def test_请求模型规范化字段并拒绝未知输入() -> None:
    """请求契约固定语法规范化和未知字段拒绝规则，业务规则仍由领域测试负责。"""

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
    # 用户名和密码可能包含有意义的空格，公共 Schema 不得擅自改写凭据。
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


@pytest.mark.parametrize("model", [CameraCreateRequest, CameraUpdateRequest])
def test_Camera视频源保留最小数量限制并使用专用空列表错误(
    model: type[BaseModel],
) -> None:
    """创建与更新都必须保留 OpenAPI 最小条目和稳定的空数组错误类型。"""

    sources_schema = model.model_json_schema()["properties"]["sources"]
    assert sources_schema["minItems"] == 1

    invalid = _model_example(model).copy()
    invalid["sources"] = []
    with pytest.raises(ValidationError) as captured:
        model.model_validate(invalid)
    safe_errors = captured.value.errors(include_input=False, include_context=False)
    assert [(error["loc"], error["type"]) for error in safe_errors] == [
        (("sources",), "camera_source_required")
    ]


@pytest.mark.parametrize(
    "model",
    [CameraCreateRequest, CameraUpdateRequest, SetDefaultPreviewSourceRequest],
)
def test_请求示例均通过对应模型验证(model: type[BaseModel]) -> None:
    """生成物中的请求 example 必须可被对应 Pydantic Schema 原样接纳。"""

    model.model_validate(_model_example(model))


@pytest.mark.parametrize(
    "model",
    [CameraDetail, CameraPage, DefaultPreviewSourceResponse],
)
def test_响应示例均通过对应模型验证(model: type[BaseModel]) -> None:
    """响应 example 必须通过 Schema 校验，不能靠手写 JSON 掩盖结构漂移。"""

    model.model_validate(_model_example(model))


def test_规范视频源ID拒绝大写文本() -> None:
    """请求体 Source UUID 与路径参数使用同一小写标准文本规则。"""

    with pytest.raises(ValidationError, match="uuid_canonical"):
        SetDefaultPreviewSourceRequest.model_validate({"source_id": CAMERA_ID_EXAMPLE.upper()})


@pytest.mark.sensitive_data
def test_列表模型递归禁止敏感字段(application: FastAPI) -> None:
    """模型图和固定 example 都不能把 Camera 连接秘密暴露到列表响应。"""

    openapi = application.openapi()
    components = openapi["components"]["schemas"]
    property_names = _collect_property_names(components["CameraPage"], components=components)
    assert property_names.isdisjoint(SENSITIVE_FIELDS)
    example_text = json.dumps(_model_example(CameraPage), ensure_ascii=False)
    assert "rtsp://" not in example_text
    assert TEST_PASSWORD not in example_text
