"""可被 Path、Query 和请求 Schema 复用的严格 HTTP 标量类型。"""

from typing import Annotated, Any
from uuid import RFC_4122, UUID

from pydantic import BeforeValidator
from pydantic_core import PydanticCustomError


def _validate_canonical_uuid4(value: Any) -> Any:
    """只接受小写、带连字符且 RFC variant 正确的 UUID v4 文本。

    标准 ``UUID`` 解析器会宽松接受大写、无连字符和花括号形式；HTTP 契约需要唯一文本表示，
    所以必须在 Pydantic 把字符串转成 UUID 前完成逐字比较。错误中不附带输入值。
    """

    if not isinstance(value, str):
        # HTTP 契约冻结的是文本表示；直接接受 UUID 对象会让 Python 内部调用绕过 canonical
        # 文本检查，并导致测试与真实 JSON 请求拥有不同语义。
        raise PydanticCustomError("uuid_canonical", "请输入标准 UUID v4。")
    try:
        parsed = UUID(value)
    except (AttributeError, ValueError):
        raise PydanticCustomError("uuid_canonical", "请输入标准 UUID v4。") from None
    if parsed.version != 4 or parsed.variant != RFC_4122 or str(parsed) != value:
        # ``str(parsed)`` 是小写带连字符标准形式，一次比较即可同时拒绝大写、花括号和无连字符
        # 输入；version/variant 则阻止其他 UUID 版本伪装成格式正确的 ID。
        raise PydanticCustomError("uuid_canonical", "请输入标准 UUID v4。")
    return value


# BeforeValidator 只收紧输入文本，底层类型仍是 UUID，因此 OpenAPI/JSON Schema 保留
# ``type: string, format: uuid``，步骤 6 无需手工修补生成契约。
CanonicalUUID4 = Annotated[UUID, BeforeValidator(_validate_canonical_uuid4)]
