"""验证测试目录只能归属于一个明确的平台、层级和模块。"""

from __future__ import annotations

import copy
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import test_changed, test_policy_check


class TestPathPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = test_changed.load_config()

    def test_接受已登记目录(self) -> None:
        with patch.object(Path, "exists", return_value=True):
            errors = test_policy_check.validate_test_paths(
                self.config,
                ["backend/tests/unit/cameras/test_values.py"],
            )

        self.assertEqual(errors, [])

    def test_拒绝平台和模块错配(self) -> None:
        with patch.object(Path, "exists", return_value=True):
            errors = test_policy_check.validate_test_paths(
                self.config,
                ["backend/tests/unit/frontend-cameras/test_wrong.py"],
            )

        self.assertEqual(len(errors), 1)
        self.assertIn("不在已登记", errors[0])

    def test_允许公共测试支持文件(self) -> None:
        with patch.object(Path, "exists", return_value=True):
            errors = test_policy_check.validate_test_paths(
                self.config,
                ["backend/tests/conftest.py", "frontend/tests/support/render.tsx"],
            )

        self.assertEqual(errors, [])

    def test_拒绝同时属于多个模块的路径(self) -> None:
        config = copy.deepcopy(self.config)
        config["modules"]["frontend-video"]["tests"].append(
            {"paths": ["frontend/tests/unit/cameras/**"], "level": "unit"}
        )

        with patch.object(Path, "exists", return_value=True):
            errors = test_policy_check.validate_test_paths(
                config,
                ["frontend/tests/unit/cameras/test_query.ts"],
            )

        self.assertEqual(len(errors), 1)
        self.assertIn("同时属于多个测试模块", errors[0])

    def test_允许删除不符合新规范的旧测试(self) -> None:
        errors = test_policy_check.validate_test_paths(
            self.config,
            ["backend/tests/modules/cameras/test_legacy.py"],
        )

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
