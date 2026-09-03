#!/usr/bin/env python3
"""根据 Git 变更选择最小但足够的测试范围，并压缩命令行输出。"""

from __future__ import annotations

import fnmatch
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "test-impact.json"
ERROR_LINE = re.compile(
    r"(?:FAILED|FAILURES|ERRORS?|AssertionError|Traceback|\berror\b|\bfatal\b|\bE\s{2,})",
    re.IGNORECASE,
)


class ConfigurationError(ValueError):
    """表示 test-impact.json 不完整或字段互相矛盾。"""


def git_paths(*args: str) -> list[str]:
    """执行只返回路径的 Git 命令；失败时停止，避免把异常误判为无变更。"""

    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "未知 Git 错误"
        raise RuntimeError(f"Git 命令执行失败：git {' '.join(args)}\n{detail}")
    return [line.replace("\\", "/") for line in result.stdout.splitlines() if line]


def changed_files(base_ref: str) -> list[str]:
    """收集分支提交、暂存区、工作区和未跟踪文件，供两个门禁使用同一变更集合。"""

    files = set(git_paths("diff", "--name-only", f"{base_ref}...HEAD"))
    files.update(git_paths("diff", "--name-only"))
    files.update(git_paths("diff", "--cached", "--name-only"))
    # 新增测试在首次 git add 前也必须接受目录检查和影响分析，否则最常见的新增文件
    # 会绕过门禁。这里只包含未被 .gitignore 排除的文件。
    files.update(git_paths("ls-files", "--others", "--exclude-standard"))
    return sorted(files)


def matches(path: str, patterns: list[str]) -> bool:
    """判断仓库相对路径是否命中至少一个配置 glob。"""

    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def is_below_root(path: str, roots: list[str]) -> bool:
    """判断路径是否位于某个目录根下，不把名称中偶然出现 tests 的源码算作测试。"""

    return any(
        path == root.rstrip("/") or path.startswith(root.rstrip("/") + "/")
        for root in roots
    )


def load_config(path: Path = CONFIG) -> dict[str, Any]:
    """读取并检查影响配置，尽早暴露拼写错误和空测试命令。"""

    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"无法读取测试影响配置：{exc}") from exc
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    """检查选择器依赖的最小配置结构及模块引用。"""

    if config.get("version") != 2:
        raise ConfigurationError("test-impact.json 版本必须是 2")

    levels = config.get("levels")
    if levels != ["unit", "module", "integration"]:
        raise ConfigurationError("levels 必须按 unit、module、integration 排列")

    modules = config.get("modules")
    if not isinstance(modules, dict) or not modules:
        raise ConfigurationError("modules 必须登记至少一个测试模块")

    known_modules = set(modules)
    for name, module in modules.items():
        if not isinstance(module, dict):
            raise ConfigurationError(f"模块 {name} 的配置必须是对象")
        if not module.get("source") and not module.get("tests"):
            raise ConfigurationError(f"模块 {name} 必须登记 source 或 tests")

        commands = module.get("commands")
        if not isinstance(commands, dict):
            raise ConfigurationError(f"模块 {name} 缺少 commands")
        for level in levels:
            values = commands.get(level)
            if (
                not isinstance(values, list)
                or not values
                or not all(isinstance(value, str) and value.strip() for value in values)
            ):
                raise ConfigurationError(f"模块 {name} 缺少 {level} 级测试命令")

        unknown_impacts = set(module.get("impacts", [])) - known_modules
        if unknown_impacts:
            raise ConfigurationError(
                f"模块 {name} 引用了未登记的影响模块：{', '.join(sorted(unknown_impacts))}"
            )

        for group in ("source", "tests"):
            for rule in module.get(group, []):
                if rule.get("level") not in levels or not rule.get("paths"):
                    raise ConfigurationError(
                        f"模块 {name} 的 {group} 规则缺少有效 level 或 paths"
                    )

    scale = config.get("scale", {})
    required_thresholds = (
        "module_files",
        "module_modules",
        "integration_files",
        "integration_modules",
    )
    if any(
        not isinstance(scale.get(key), int) or scale[key] < 1
        for key in required_thresholds
    ):
        raise ConfigurationError("scale 的文件数和模块数阈值必须是正整数")
    if (
        scale["integration_files"] < scale["module_files"]
        or scale["integration_modules"] < scale["module_modules"]
    ):
        raise ConfigurationError("integration 阈值不能小于 module 阈值")


def _raise_level(current: str, requested: str, levels: list[str]) -> str:
    """返回两个验证级别中更高的一个。"""

    return requested if levels.index(requested) > levels.index(current) else current


def select_verification(
    config: dict[str, Any], changed: list[str]
) -> tuple[str, list[str], list[str]]:
    """返回验证级别、受影响模块和未登记但不能忽略的路径。"""

    levels = config["levels"]
    selected: dict[str, str] = {}
    relevant_files: set[str] = set()
    unmatched: list[str] = []

    for path in changed:
        path_matched = False
        for name, module in config["modules"].items():
            for group in ("source", "tests"):
                for rule in module.get(group, []):
                    if matches(path, rule["paths"]):
                        relevant_files.add(path)
                        previous = selected.get(name, levels[0])
                        selected[name] = _raise_level(previous, rule["level"], levels)
                        path_matched = True

        # 迁移可能删除尚未登记的旧源码旁测试或测试工具。只对可识别的测试路径放行删除，
        # 避免把拼错或遗漏登记的普通生产源码误判成已删除旧文件。同一路径只要仍然存在，
        # 就必须命中模块或 ignored_paths；已登记路径即使被删除也会在上方触发对应模块。
        path_parts = Path(path).parts
        deleted_unregistered_test = not (ROOT / path).exists() and (
            is_below_root(path, config.get("test_roots", []))
            or "test" in path_parts
            or Path(path).name.endswith((".test.ts", ".test.tsx", "_test.py"))
        )
        if (
            not path_matched
            and not deleted_unregistered_test
            and not matches(path, config.get("ignored_paths", []))
        ):
            unmatched.append(path)

    if not selected:
        return levels[0], [], unmatched

    # 依赖模块加入后至少执行 module 级验证，因为单元测试无法覆盖跨模块协作。
    queue = list(selected)
    while queue:
        current = queue.pop()
        for downstream in config["modules"][current].get("impacts", []):
            requested = config.get("impact_level", "module")
            previous = selected.get(downstream, levels[0])
            raised = _raise_level(previous, requested, levels)
            if downstream not in selected:
                selected[downstream] = raised
                queue.append(downstream)
            else:
                selected[downstream] = raised

    level = levels[0]
    for requested in selected.values():
        level = _raise_level(level, requested, levels)

    # 文件数防止单模块大改仍只跑零散单测；模块数则直接反映跨边界变更规模。
    scale = config["scale"]
    if (
        len(relevant_files) >= scale["module_files"]
        or len(selected) >= scale["module_modules"]
    ):
        level = _raise_level(level, "module", levels)
    if (
        len(relevant_files) >= scale["integration_files"]
        or len(selected) >= scale["integration_modules"]
    ):
        level = _raise_level(level, "integration", levels)

    return level, sorted(selected), unmatched


def commands_for(
    config: dict[str, Any], modules: list[str], level: str
) -> list[tuple[str, str]]:
    """按模块生成命令并去重，避免共享命令被重复执行。"""

    commands: list[tuple[str, str]] = []
    seen: set[str] = set()
    for module in modules:
        for command in config["modules"][module]["commands"][level]:
            if command not in seen:
                commands.append((module, command))
                seen.add(command)
    return commands


def _print_failure_excerpt(log_path: Path) -> None:
    """只打印少量关键失败行；完整输出保留给后续 rg 定点查看。"""

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    matches_found = [line for line in lines if ERROR_LINE.search(line)]
    excerpt = matches_found[-40:] if matches_found else lines[-25:]
    if excerpt:
        print("失败摘要：")
        for line in excerpt:
            print(f"  {line[:500]}")


def run_commands(commands: list[tuple[str, str]]) -> int:
    """顺序执行命令，将大段输出写入临时日志，只向终端提供结果摘要。"""

    log_dir = Path(tempfile.mkdtemp(prefix="sop-vision-verify-"))
    print(f"测试日志目录：{log_dir}")

    for index, (module, command) in enumerate(commands, start=1):
        safe_module = re.sub(r"[^a-zA-Z0-9_.-]+", "-", module)
        log_path = log_dir / f"{index:02d}-{safe_module}.log"
        started = time.monotonic()
        with log_path.open("w", encoding="utf-8") as output:
            # 命令本身只写入日志，成功时不占用终端上下文；失败后仍可完整还原执行现场。
            output.write(f"$ {command}\n\n")
            output.flush()
            result = subprocess.run(
                ["bash", "-o", "pipefail", "-c", command],
                cwd=ROOT,
                stdout=output,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
        elapsed = time.monotonic() - started
        if result.returncode != 0:
            print(f"失败：{module}（{elapsed:.1f}s，退出码 {result.returncode}）")
            print(f"完整日志：{log_path}")
            _print_failure_excerpt(log_path)
            return result.returncode
        print(f"通过：{module}（{elapsed:.1f}s）")

    return 0


def main() -> int:
    """命令行入口。"""

    try:
        config = load_config()
        changed = changed_files(config.get("base_ref", "origin/main"))
        if not changed:
            print("变更测试：没有待检查文件")
            return 0

        level, modules, unmatched = select_verification(config, changed)
        if unmatched:
            print("变更测试：以下路径未登记测试影响，也未明确忽略：")
            for path in unmatched:
                print(f"  - {path}")
            return 2
        if not modules:
            print("变更测试：本次只有文档或工具配置变更，无需运行测试")
            return 0

        print(f"变更测试：级别={level}，模块={', '.join(modules)}")
        return run_commands(commands_for(config, modules, level))
    except (ConfigurationError, RuntimeError) as exc:
        print(f"变更测试：{exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
