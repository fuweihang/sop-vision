"""验证变更测试选择器的范围判断和紧凑日志行为。"""

from __future__ import annotations

import contextlib
import io
import unittest
from unittest.mock import patch

from scripts import test_changed


class ChangedFilesTests(unittest.TestCase):
    """变更集合必须覆盖日常开发可能出现的四种 Git 状态。"""

    def test_包含未跟踪文件(self) -> None:
        outputs = {
            ("diff", "--name-only", "origin/main...HEAD"): ["committed.py"],
            ("diff", "--name-only"): ["working.py"],
            ("diff", "--cached", "--name-only"): ["staged.py"],
            ("ls-files", "--others", "--exclude-standard"): ["untracked.py"],
        }

        with patch.object(
            test_changed, "git_paths", side_effect=lambda *args: outputs[args]
        ):
            files = test_changed.changed_files("origin/main")

        self.assertEqual(
            files,
            ["committed.py", "staged.py", "untracked.py", "working.py"],
        )


class SelectionTests(unittest.TestCase):
    """风险路径、影响传播和变更规模应逐级提高验证范围。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = test_changed.load_config()

    def test_领域内部小改只运行单元测试(self) -> None:
        level, modules, unmatched = test_changed.select_verification(
            self.config,
            ["backend/src/app/modules/cameras/domain/values.py"],
        )

        self.assertEqual(level, "unit")
        self.assertEqual(modules, ["backend-cameras"])
        self.assertEqual(unmatched, [])

    def test_API改动提升到模块测试并传播到跨端模块(self) -> None:
        level, modules, unmatched = test_changed.select_verification(
            self.config,
            ["backend/src/app/modules/cameras/api/router.py"],
        )

        self.assertEqual(level, "module")
        self.assertEqual(
            modules,
            ["api-contract", "backend-cameras", "frontend-cameras"],
        )
        self.assertEqual(unmatched, [])

    def test_持久化改动直接运行集成测试(self) -> None:
        level, modules, unmatched = test_changed.select_verification(
            self.config,
            ["backend/src/app/modules/cameras/persistence/repository.py"],
        )

        self.assertEqual(level, "integration")
        self.assertEqual(modules, ["backend-cameras"])
        self.assertEqual(unmatched, [])

    def test_单模块大范围改动也提升到集成测试(self) -> None:
        paths = [
            f"backend/src/app/modules/cameras/domain/generated_{index}.py"
            for index in range(self.config["scale"]["integration_files"])
        ]

        level, modules, unmatched = test_changed.select_verification(self.config, paths)

        self.assertEqual(level, "integration")
        self.assertEqual(modules, ["backend-cameras"])
        self.assertEqual(unmatched, [])

    def test_未知源码不能静默跳过(self) -> None:
        level, modules, unmatched = test_changed.select_verification(
            self.config,
            ["backend/src/app/modules/detectors/service.py"],
        )

        self.assertEqual(level, "unit")
        self.assertEqual(modules, [])
        self.assertEqual(unmatched, ["backend/src/app/modules/detectors/service.py"])

    def test_允许删除尚未迁移的旧测试路径(self) -> None:
        level, modules, unmatched = test_changed.select_verification(
            self.config,
            ["backend/tests/modules/cameras/test_legacy.py"],
        )

        self.assertEqual(level, "unit")
        self.assertEqual(modules, [])
        self.assertEqual(unmatched, [])


class CommandOutputTests(unittest.TestCase):
    """大量测试输出不得直接灌入 AI 上下文。"""

    def test_成功命令只打印摘要(self) -> None:
        terminal = io.StringIO()
        with contextlib.redirect_stdout(terminal):
            result = test_changed.run_commands(
                [("示例模块", "python3 -c \"print('x' * 10000)\"")]
            )

        output = terminal.getvalue()
        self.assertEqual(result, 0)
        self.assertIn("通过：示例模块", output)
        self.assertNotIn("x" * 100, output)

    def test_失败命令只摘取关键错误并保留日志(self) -> None:
        terminal = io.StringIO()
        with contextlib.redirect_stdout(terminal):
            result = test_changed.run_commands(
                [("示例模块", "printf '普通输出\\nERROR: 示例失败\\n'; exit 3")]
            )

        output = terminal.getvalue()
        self.assertEqual(result, 3)
        self.assertIn("ERROR: 示例失败", output)
        self.assertIn("完整日志：", output)


if __name__ == "__main__":
    unittest.main()
