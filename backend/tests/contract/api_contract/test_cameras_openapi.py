"""Cameras 公共 OpenAPI 与导出结果的兼容性测试。"""

from pathlib import Path

from fastapi import FastAPI

from app.core.http.problems import PROBLEM_MEDIA_TYPE, ProblemDetails
from scripts.export_openapi import build_openapi_document, export_openapi, serialize_openapi

EXPECTED_CAMERA_OPERATIONS = {
    ("/api/v1/cameras", "get"): ("listCameras", {"200", "422", "500", "503"}),
    ("/api/v1/cameras", "post"): ("createCamera", {"201", "422", "503"}),
    ("/api/v1/cameras/{camera_id}", "get"): (
        "getCamera",
        {"200", "404", "422", "500", "503"},
    ),
    ("/api/v1/cameras/{camera_id}", "put"): (
        "updateCamera",
        {"200", "404", "422", "500", "503"},
    ),
    ("/api/v1/cameras/{camera_id}/default-preview-source", "patch"): (
        "setDefaultPreviewSource",
        {"200", "404", "422", "500", "503"},
    ),
    ("/api/v1/cameras/{camera_id}", "delete"): (
        "deleteCamera",
        {"204", "404", "422", "503"},
    ),
}


def test_OpenAPI包含准确的目标路径操作响应和标签(
    application: FastAPI,
) -> None:
    """六条公共路径必须保留稳定的客户端方法名、响应集合和 Cameras 标签。"""

    openapi = application.openapi()
    for (path, method), (operation_id, statuses) in EXPECTED_CAMERA_OPERATIONS.items():
        operation = openapi["paths"][path][method]
        assert operation["operationId"] == operation_id
        assert set(operation["responses"]) == statuses
        assert operation["tags"] == ["cameras"]
        for response in operation["responses"].values():
            assert "X-Trace-Id" in response["headers"]


def test_OpenAPI使用问题详情媒体类型和必需协议响应头(
    application: FastAPI,
) -> None:
    """错误媒体类型和成功响应 header 必须在生成 Frontend Client 前固定下来。"""

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
    assert (
        "content"
        not in openapi["paths"]["/api/v1/cameras/{camera_id}"]["delete"]["responses"]["204"]
    )


def test_问题详情示例有效且OpenAPI导出结果逐字节稳定(tmp_path: Path) -> None:
    """导出不得依赖 lifespan，同一文档连续生成及写盘必须得到相同 UTF-8 字节。"""

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
