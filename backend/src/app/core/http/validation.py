"""把 FastAPI/Pydantic 校验位置与错误类型转换为稳定公共契约。"""

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from app.core.http.problems import FieldError

# FastAPI 在 loc 首段加入输入来源，但前端字段映射只需要业务字段路径。来源集合显式列出，
# 避免误删一个恰好名为其他字符串的真实顶层字段。
_LOCATION_PREFIXES = {"body", "path", "query", "header", "cookie"}


def validation_location_to_field(location: Sequence[str | int]) -> str:
    """把 Pydantic location 转为前端表单可消费的字段路径。

    例如 ``('body', 'sources', 1, 'name')`` 转为 ``sources[1].name``。整体验证或 JSON 解析
    错误没有业务字段时统一落到 ``body``，而不是返回空字符串导致前端无法展示。
    """

    parts = list(location)
    if parts and parts[0] in _LOCATION_PREFIXES:
        parts.pop(0)
    if not parts:
        return "body"

    field = ""
    for part in parts:
        if isinstance(part, int):
            # 数组下标必须使用方括号；若写成 ``sources.1.name``，React Hook Form 等调用方
            # 可能无法准确定位动态列表中的对应行。
            field += f"[{part}]"
        elif field:
            field += f".{part}"
        else:
            field = str(part)
    return field


def _public_validation_code(error_type: str) -> str:
    """只根据 Pydantic 稳定错误类型分类，绝不读取可能含原始输入的错误上下文。"""

    # 这里只依赖 Pydantic 的机器错误类型，绝不比较本地化 msg，也不读取可能包含输入值的 ctx。
    if error_type == "camera_source_required":
        return "SOURCE_REQUIRED"
    if error_type == "extra_forbidden":
        return "UNKNOWN_FIELD"
    if error_type == "missing" or error_type == "string_too_short":
        return "REQUIRED"
    if error_type == "string_too_long":
        return "STRING_TOO_LONG"
    if error_type == "ip_v4_address":
        return "INVALID_IP_ADDRESS"
    if error_type.startswith("uuid_") or error_type == "uuid_canonical":
        return "INVALID_UUID"
    if error_type in {
        "greater_than",
        "greater_than_equal",
        "int_parsing",
        "int_type",
        "less_than",
        "less_than_equal",
        "too_long",
        "too_short",
    }:
        return "OUT_OF_RANGE"
    return "INVALID_VALUE"


# detail 采用固定文本，不拼接限制值或原始输入；稳定 code 才是前端业务分支的事实来源。
_PUBLIC_DETAILS = {
    "SOURCE_REQUIRED": "创建 Camera 至少需要一路 Source。",
    "UNKNOWN_FIELD": "该字段不受支持。",
    "REQUIRED": "该字段不能为空。",
    "STRING_TOO_LONG": "该字段超过允许的最大长度。",
    "INVALID_IP_ADDRESS": "请输入合法的 IPv4 地址。",
    "INVALID_UUID": "请输入小写、带连字符的标准 UUID v4。",
    "OUT_OF_RANGE": "该字段超出允许范围。",
    "INVALID_VALUE": "该字段值无效。",
}


def convert_validation_errors(errors: Iterable[Mapping[str, Any]]) -> tuple[FieldError, ...]:
    """把 Pydantic 错误集合转换为公开字段错误。

    输入顺序原样保留，使同字段多错误和动态数组错误具有确定顺序。转换只提取 ``loc/type``，
    主动丢弃 ``input/msg/ctx/url`` 等可能泄密或随依赖版本变化的字段。
    """

    converted: list[FieldError] = []
    for error in errors:
        location = error.get("loc", ())
        # Pydantic location 正常只含字符串与整数；过滤其他对象可防止第三方自定义校验器把
        # 可打印的任意对象带入公开字段路径。
        safe_location = tuple(part for part in location if isinstance(part, (str, int)))
        code = _public_validation_code(str(error.get("type", "")))
        converted.append(
            FieldError(
                field=validation_location_to_field(safe_location),
                code=code,
                detail=_PUBLIC_DETAILS[code],
            )
        )
    return tuple(converted)
