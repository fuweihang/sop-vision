#!/usr/bin/env python3
"""检查仓库中全部现存测试是否位于已登记的层级和模块目录。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# 直接执行本文件时，Python 只把 scripts/ 放入模块搜索路径；显式加入该目录可让测试和
# 命令行入口复用同一份变更收集与配置校验逻辑，而不复制容易漂移的 Git 处理代码。
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from test_changed import (
    CONFIG,
    ROOT,
    ConfigurationError,
    is_below_root,
    load_config,
    matches,
    repository_files,
)


def _module_owners(config: dict[str, Any], path: str, group: str) -> list[str]:
    """返回通过 source 或 tests 规则明确拥有该路径的模块。"""

    owners: list[str] = []
    for name, module in config["modules"].items():
        if any(matches(path, rule["paths"]) for rule in module.get(group, [])):
            owners.append(name)
    return owners


def _is_source_test(path: str) -> bool:
    """识别迁移完成后禁止重新出现的 Backend/Frontend 源码旁测试。"""

    filename = Path(path).name
    if is_below_root(path, ["backend/src"]):
        return filename.startswith("test_") and filename.endswith(".py") or (
            filename.endswith("_test.py")
        )

    if not is_below_root(path, ["frontend/src"]):
        return False
    if is_below_root(path, ["frontend/src/test"]):
        return True
    return filename.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))


def validate_test_paths(config: dict[str, Any], repository_paths: list[str]) -> list[str]:
    """返回测试路径错误；合法路径必须且只能归属于一个已登记模块。"""

    errors: list[str] = []
    roots = config.get("test_roots", [])
    support_paths = config.get("test_support_paths", [])

    for path in repository_paths:
        # 删除旧路径是在修正问题，不能要求一个已经不存在的文件仍满足新目录规则。
        # rename 的新路径仍然存在，因此会在后续逻辑中正常接受检查。
        if not (ROOT / path).exists():
            continue

        if _is_source_test(path):
            errors.append(f"{path}：源码目录中存在测试文件，请迁移到标准测试目录")
            continue

        if not is_below_root(path, roots):
            continue
        if matches(path, support_paths):
            # `__init__.py` 只建立 Python 包边界，没有运行行为；其他 Support 必须用
            # source 规则明确登记使用模块和最低测试级别，不能靠宽泛 support glob 静默跳过。
            if Path(path).name != "__init__.py" and not _module_owners(
                config, path, "source"
            ):
                errors.append(f"{path}：测试支持文件没有登记受影响模块")
            continue

        owners = _module_owners(config, path, "tests")

        if not owners:
            errors.append(f"{path}：不在已登记的测试层级和模块目录中")
        elif len(owners) > 1:
            errors.append(f"{path}：同时属于多个测试模块：{', '.join(sorted(owners))}")

    return errors


def main() -> int:
    """命令行入口。"""

    try:
        config = load_config(CONFIG)
        errors = validate_test_paths(config, repository_files())
    except (ConfigurationError, RuntimeError) as exc:
        print(f"测试目录检查：{exc}")
        return 2

    if errors:
        print("测试目录检查：失败")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("测试目录检查：通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
