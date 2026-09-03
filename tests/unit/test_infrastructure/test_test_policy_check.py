"""验证测试目录只能归属于一个明确的平台、层级和模块。"""

from __future__ import annotations

import copy
import contextlib
import io
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
                [
                    "backend/tests/unit/cameras/test_values.py",
                    "backend/tests/module/cameras/test_camera_detail.py",
                    "backend/tests/integration/cameras/test_repository_behavior.py",
                    "backend/tests/contract/api_contract/test_cameras_openapi.py",
                    "frontend/tests/contract/api_contract/cameras-contract-security.test.ts",
                    "frontend/tests/unit/cameras/query-keys.test.ts",
                    "frontend/tests/component/cameras/card.test.tsx",
                    "frontend/tests/contract/cameras/api.test.ts",
                    "frontend/tests/integration/cameras/routes.test.tsx",
                    "frontend/tests/unit/video/geometry.test.ts",
                    "frontend/tests/component/video/controls.test.tsx",
                    "frontend/tests/contract/video/whep-session.test.ts",
                    "frontend/tests/integration/video/session.test.tsx",
                    "frontend/tests/unit/shared/route-meta.test.ts",
                    "frontend/tests/component/shared/button.test.tsx",
                    "frontend/tests/contract/shared/api-client.test.ts",
                    "frontend/tests/integration/shared/providers.test.tsx",
                    "frontend/tests/unit/app_shell/navigation.test.ts",
                    "frontend/tests/component/app_shell/header.test.tsx",
                    "frontend/tests/contract/app_shell/routes.test.ts",
                    "frontend/tests/integration/app_shell/layout.test.tsx",
                ],
            )

        self.assertEqual(errors, [])

    def test_APIContract目录不能同时登记到Cameras模块(self) -> None:
        """公共契约必须直接归 api-contract，不能再经过 contract/cameras 中转。"""

        config = copy.deepcopy(self.config)
        config["modules"]["backend-cameras"]["tests"].append(
            {
                "paths": ["backend/tests/contract/api_contract/**"],
                "level": "module",
            }
        )

        with patch.object(Path, "exists", return_value=True):
            errors = test_policy_check.validate_test_paths(
                config,
                ["backend/tests/contract/api_contract/test_cameras_openapi.py"],
            )

        self.assertEqual(len(errors), 1)
        self.assertIn("同时属于多个测试模块", errors[0])

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
                [
                    "backend/tests/conftest.py",
                    "backend/tests/support/cameras/builders.py",
                    "frontend/tests/setup.ts",
                    "frontend/tests/support/render-router.tsx",
                ],
            )

        self.assertEqual(errors, [])

    def test_拒绝没有影响登记的测试支持文件(self) -> None:
        """Support 不能只靠宽泛目录通配绕过模块选择。"""

        with patch.object(Path, "exists", return_value=True):
            errors = test_policy_check.validate_test_paths(
                self.config,
                ["frontend/tests/support/orphan.ts"],
            )

        self.assertEqual(len(errors), 1)
        self.assertIn("没有登记受影响模块", errors[0])

    def test_允许没有运行行为的包初始化文件(self) -> None:
        """Python 包文件不包含 Fixture 或 Mock，不要求虚构一个使用模块。"""

        with patch.object(Path, "exists", return_value=True):
            errors = test_policy_check.validate_test_paths(
                self.config,
                ["backend/tests/__init__.py"],
            )

        self.assertEqual(errors, [])

    def test_接受StreamGateway新目录并拒绝仍存在的旧目录(self) -> None:
        """迁移后的三层目录有明确归属，旧 modules 目录不能重新引入。"""

        with patch.object(Path, "exists", return_value=True):
            errors = test_policy_check.validate_test_paths(
                self.config,
                [
                    "backend/tests/unit/stream_gateway/test_ports.py",
                    "backend/tests/contract/stream_gateway/test_mediamtx_openapi.py",
                    "backend/tests/integration/stream_gateway/test_mediamtx_adapter.py",
                ],
            )
            legacy_errors = test_policy_check.validate_test_paths(
                self.config,
                ["backend/tests/modules/stream_gateway/test_ports.py"],
            )

        self.assertEqual(errors, [])
        self.assertEqual(len(legacy_errors), 1)
        self.assertIn("不在已登记", legacy_errors[0])

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

    def test_拒绝Backend和Frontend源码旁测试(self) -> None:
        """迁移完成后，常见测试命名和 frontend/src/test 都不能重新出现。"""

        paths = [
            "backend/src/app/modules/cameras/test_values.py",
            "backend/src/app/modules/cameras/values_test.py",
            "frontend/src/features/cameras/card.test.ts",
            "frontend/src/features/cameras/card.test.tsx",
            "frontend/src/features/cameras/card.spec.ts",
            "frontend/src/features/cameras/card.spec.tsx",
            "frontend/src/test/setup.ts",
        ]
        with patch.object(Path, "exists", return_value=True):
            errors = test_policy_check.validate_test_paths(self.config, paths)

        self.assertEqual(len(errors), len(paths))
        for path, error in zip(paths, errors, strict=True):
            self.assertIn(path, error)
            self.assertIn("源码目录中存在测试文件", error)

    def test_允许删除不符合新规范的旧测试(self) -> None:
        errors = test_policy_check.validate_test_paths(
            self.config,
            ["backend/tests/legacy/cameras/test_legacy.py"],
        )

        self.assertEqual(errors, [])

    def test_命令行检查使用全部仓库文件而不是Git变更集合(self) -> None:
        """目录门禁必须持续发现历史遗留测试，不能只验证当前 diff。"""

        repository_paths = ["backend/tests/unit/cameras/test_values.py"]
        terminal = io.StringIO()
        with (
            patch.object(
                test_policy_check,
                "repository_files",
                return_value=repository_paths,
            ) as repository_files,
            patch.object(
                test_policy_check,
                "validate_test_paths",
                return_value=[],
            ) as validate_test_paths,
            contextlib.redirect_stdout(terminal),
        ):
            result = test_policy_check.main()

        self.assertEqual(result, 0)
        repository_files.assert_called_once_with()
        validate_test_paths.assert_called_once_with(self.config, repository_paths)
        self.assertIn("测试目录检查：通过", terminal.getvalue())


if __name__ == "__main__":
    unittest.main()
