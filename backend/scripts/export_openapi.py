"""从真实应用路由树确定性导出跨端 OpenAPI 契约。"""

import json
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from app.core.config import Settings
from app.factory import create_app

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_PATH = REPOSITORY_ROOT / "contracts" / "openapi.json"
# 该地址只满足 Settings 的语法校验；导出不会进入 lifespan，所以不会创建 Engine 或连接它。
OPENAPI_DATABASE_URL = "postgresql+psycopg://openapi:openapi@127.0.0.1:5432/openapi_contract"


def build_openapi_document() -> dict[str, Any]:
    """使用固定元数据创建真实应用 Schema，不读取环境配置或启动任何依赖。"""

    settings = Settings(
        app_name="SOP Vision 后端",
        database_url=SecretStr(OPENAPI_DATABASE_URL),
        backend_cors_origins=["http://localhost:8000"],
    )
    return create_app(settings=settings).openapi()


def serialize_openapi(document: dict[str, Any]) -> bytes:
    """排序全部对象键并固定 UTF-8、两空格缩进和尾换行，保证字节级可重复。"""

    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode()


def export_openapi(output_path: Path = DEFAULT_OUTPUT_PATH) -> bytes:
    """生成并写入契约；返回相同字节便于测试连续生成稳定性。"""

    content = serialize_openapi(build_openapi_document())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(content)
    return content


if __name__ == "__main__":
    export_openapi()
