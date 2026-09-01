"""防止具体 Worker 或算法实现重新形成双向依赖。"""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
SOURCE_ROOT = PROJECT_ROOT / "src" / "algorithm"


def imported_modules(package: Path) -> set[str]:
    """收集包内 Python 文件的绝对导入，测试只关心模块边界。"""

    modules: set[str] = set()
    for source in package.rglob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                # 保留相对导入前缀，确保 ``from ..tracker`` 这类写法也会被边界
                # 测试发现，而不是只有绝对导入才受检查。
                modules.add(f"{'.' * node.level}{node.module}")
    return modules


def test_detector和tracker_worker禁止互相导入() -> None:
    detector_imports = imported_modules(SOURCE_ROOT / "workers" / "detector")
    tracker_imports = imported_modules(SOURCE_ROOT / "workers" / "tracker")

    assert not any(
        module.startswith("algorithm.workers.tracker")
        or module.lstrip(".").startswith("tracker")
        for module in detector_imports
    )
    assert not any(
        module.startswith("algorithm.workers.detector")
        or module.lstrip(".").startswith("detector")
        for module in tracker_imports
    )


def test_detection和tracking算法禁止互相导入() -> None:
    detection_imports = imported_modules(
        SOURCE_ROOT / "algorithms" / "object_detection"
    )
    tracking_imports = imported_modules(
        SOURCE_ROOT / "algorithms" / "object_tracking"
    )

    assert not any("object_tracking" in module for module in detection_imports)
    assert not any("object_detection" in module for module in tracking_imports)
