#!/usr/bin/env python3
"""检查新增或修改的测试是否位于已登记的层级和模块目录。"""

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
    changed_files,
    is_below_root,
    load_config,
    matches,
)


def validate_test_paths(config: dict[str, Any], changed: list[str]) -> list[str]:
    """返回测试路径错误；合法路径必须且只能归属于一个已登记模块。"""

    errors: list[str] = []
    roots = config.get("test_roots", [])
    support_paths = config.get("test_support_paths", [])

    for path in changed:
        if not is_below_root(path, roots):
            continue
        # 删除旧路径是在修正问题，不能要求一个已经不存在的文件仍满足新目录规则。
        # rename 的新路径仍然存在，因此会在后续逻辑中正常接受检查。
        if not (ROOT / path).exists():
            continue
        if matches(path, support_paths):
            continue

        owners: list[str] = []
        for name, module in config["modules"].items():
            if any(matches(path, rule["paths"]) for rule in module.get("tests", [])):
                owners.append(name)

        if not owners:
            errors.append(f"{path}：不在已登记的测试层级和模块目录中")
        elif len(owners) > 1:
            errors.append(f"{path}：同时属于多个测试模块：{', '.join(sorted(owners))}")

    return errors


def main() -> int:
    """命令行入口。"""

    try:
        config = load_config(CONFIG)
        changed = changed_files(config.get("base_ref", "origin/main"))
        errors = validate_test_paths(config, changed)
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
