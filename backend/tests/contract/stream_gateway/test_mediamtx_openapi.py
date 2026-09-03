"""MediaMTX 版本与仓库内受控协议输入的一致性门禁。"""

import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CONTROLLED_OPENAPI = REPOSITORY_ROOT / "contracts/mediamtx-openapi.json"


def test_controlled_openapi_matches_locked_mediamtx_version() -> None:
    """Compose、示例环境和协议输入必须指向同一个精确版本。"""

    document = json.loads(CONTROLLED_OPENAPI.read_text(encoding="utf-8"))
    compose = (REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8")
    environment = (REPOSITORY_ROOT / ".env.example").read_text(encoding="utf-8")

    assert document["info"]["version"] == "1.20.1"
    assert document["x-upstream"]["tag"] == "v1.20.1"
    assert "bluenviron/mediamtx:${MEDIAMTX_IMAGE_TAG:-1.20.1}" in compose
    assert "MEDIAMTX_IMAGE_TAG=1.20.1" in environment


def test_controlled_openapi_contains_only_required_operations_and_fields() -> None:
    """03 Adapter 只能依赖经过真实版本验证的最小接口集合。"""

    document = json.loads(CONTROLLED_OPENAPI.read_text(encoding="utf-8"))
    operations = {
        (path, method, operation["operationId"])
        for path, path_item in document["paths"].items()
        for method, operation in path_item.items()
    }

    assert operations == {
        ("/v3/config/paths/list", "get", "configPathsList"),
        ("/v3/config/paths/get/{name}", "get", "configPathsGet"),
        ("/v3/config/paths/replace/{name}", "post", "configPathsReplace"),
        ("/v3/config/paths/delete/{name}", "delete", "configPathsDelete"),
        ("/v3/paths/list", "get", "pathsList"),
    }
    schemas = document["components"]["schemas"]
    assert schemas["Path"]["properties"]["available"]["type"] == "boolean"
    assert schemas["Path"]["properties"]["online"]["type"] == "boolean"
    assert schemas["PathConf"]["properties"]["sourceOnDemand"]["type"] == "boolean"
