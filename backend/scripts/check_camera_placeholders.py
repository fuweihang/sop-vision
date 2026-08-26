"""检查 Cameras handler 的 Foundation/MVP 生命周期边界。"""

import argparse
import ast
import inspect
from dataclasses import dataclass
from enum import StrEnum

from app.modules.cameras.api import router as camera_router_module


class GateMode(StrEnum):
    """Foundation 允许纯占位；MVP 发布要求所有业务 handler 已实现。"""

    FOUNDATION = "foundation"
    MVP = "mvp"


CAMERA_HANDLERS = (
    camera_router_module.list_cameras,
    camera_router_module.create_camera,
    camera_router_module.get_camera,
    camera_router_module.update_camera,
    camera_router_module.set_default_preview_source,
    camera_router_module.delete_camera,
    camera_router_module.get_camera_source_playback,
)


@dataclass(frozen=True, slots=True)
class PlaceholderReport:
    """返回可被测试和 CLI 同时消费的稳定检查结果。"""

    placeholders: tuple[str, ...]
    invalid_handlers: tuple[str, ...]


def _raises_not_implemented(node: ast.AST) -> bool:
    """只识别直接 ``raise NotImplementedError``，不把业务异常误判为占位。"""

    return (
        isinstance(node, ast.Raise)
        and isinstance(node.exc, ast.Name)
        and node.exc.id == "NotImplementedError"
    )


def analyze_camera_placeholders() -> PlaceholderReport:
    """分类七个冻结 handler，并拒绝夹带临时代码的半占位实现。

    后续切片可以把 handler 原位替换成完整实现；只要函数中不再残留 ``NotImplementedError``，
    Foundation 门禁就会把它视为已实现。若函数仍含占位异常，则函数体必须严格只有这一条语句，
    避免临时依赖、数据库写入或伪错误协议在正式业务测试到位前进入运行时。
    """

    placeholders: list[str] = []
    invalid_handlers: list[str] = []
    for handler in CAMERA_HANDLERS:
        tree = ast.parse(inspect.getsource(handler))
        function = next(node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef))
        direct_placeholder = len(function.body) == 1 and _raises_not_implemented(function.body[0])
        contains_placeholder = any(_raises_not_implemented(node) for node in ast.walk(function))

        if direct_placeholder:
            placeholders.append(handler.__name__)
        elif contains_placeholder:
            invalid_handlers.append(handler.__name__)

    return PlaceholderReport(tuple(placeholders), tuple(invalid_handlers))


def check_camera_placeholders(mode: GateMode) -> PlaceholderReport:
    """执行指定阶段门禁；失败文本只包含公开 handler 名称。"""

    report = analyze_camera_placeholders()
    if report.invalid_handlers:
        names = ", ".join(report.invalid_handlers)
        raise RuntimeError(f"以下 handler 混入了非纯占位逻辑：{names}")
    if mode is GateMode.MVP and report.placeholders:
        names = ", ".join(report.placeholders)
        raise RuntimeError(f"MVP 发布禁止残留占位 handler：{names}")
    return report


def main() -> None:
    """提供 CI 与开发者共用的显式阶段参数，避免发布检查依赖环境猜测。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=tuple(GateMode), type=GateMode)
    arguments = parser.parse_args()

    try:
        report = check_camera_placeholders(arguments.mode)
    except RuntimeError as error:
        # CLI 失败属于预期门禁结果，不输出包含调用栈的噪声；单元测试仍可直接调用函数断言异常。
        parser.exit(1, f"Cameras handler 门禁失败：{error}\n")
    if report.placeholders:
        print(
            f"Cameras {arguments.mode.value} 门禁通过；保留 {len(report.placeholders)} 个纯占位。"
        )
    else:
        print(f"Cameras {arguments.mode.value} 门禁通过；全部 handler 已实现。")


if __name__ == "__main__":
    main()
