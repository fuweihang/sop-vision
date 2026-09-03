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

    def test_Backend公共应用Fixture改动验证全部使用者(self) -> None:
        """共享应用 Fixture 变化必须运行 Core、业务模块和 API Contract。"""

        level, modules, unmatched = test_changed.select_verification(
            self.config,
            ["backend/tests/support/application.py"],
        )

        # 该 Fixture 同时影响 Core 和 API Contract，两者向下传播后达到
        # integration 的跨模块阈值。这里固定最终选择结果，避免只检查初始规则。
        self.assertEqual(level, "integration")
        self.assertEqual(
            modules,
            [
                "api-contract",
                "backend-cameras",
                "backend-core",
                "backend-stream-gateway",
                "frontend-cameras",
            ],
        )
        self.assertEqual(unmatched, [])

    def test_Backend公共数据库Support改动运行Core和Cameras集成测试(self) -> None:
        """建库、迁移或清理辅助代码变化不能只运行不访问 PostgreSQL 的 module 测试。"""

        level, modules, unmatched = test_changed.select_verification(
            self.config,
            ["backend/tests/support/database.py"],
        )

        self.assertEqual(level, "integration")
        self.assertEqual(
            modules,
            ["backend-cameras", "backend-core", "backend-stream-gateway"],
        )
        self.assertEqual(unmatched, [])
        commands = "\n".join(
            command
            for _, command in test_changed.commands_for(self.config, modules, level)
        )
        self.assertIn("tests/integration/cameras", commands)
        self.assertIn("tests/integration/core", commands)

    def test_Cameras专用Fixture按Integration级只选择Cameras模块(self) -> None:
        """领域专用 Fixture 可影响真实数据库，因此必须执行 Cameras 完整验证链。"""

        level, modules, unmatched = test_changed.select_verification(
            self.config,
            ["backend/tests/support/cameras/builders.py"],
        )

        self.assertEqual(level, "integration")
        self.assertEqual(modules, ["backend-cameras"])
        self.assertEqual(unmatched, [])

    def test_Cameras模块测试按Module级选择Cameras模块(self) -> None:
        """迁移后的查询流程测试必须按新目录触发 Cameras module 级验证。"""

        level, modules, unmatched = test_changed.select_verification(
            self.config,
            ["backend/tests/module/cameras/test_camera_detail.py"],
        )

        self.assertEqual(level, "module")
        self.assertEqual(modules, ["backend-cameras"])
        self.assertEqual(unmatched, [])

    def test_Cameras集成测试按Integration级选择Cameras模块(self) -> None:
        """真实数据库测试变化必须执行完整 Cameras integration 验证链。"""

        level, modules, unmatched = test_changed.select_verification(
            self.config,
            ["backend/tests/integration/cameras/test_repository_behavior.py"],
        )

        self.assertEqual(level, "integration")
        self.assertEqual(modules, ["backend-cameras"])
        self.assertEqual(unmatched, [])

    def test_APIContract测试按Module级选择跨端相关模块(self) -> None:
        """公共契约测试变化必须复验生成物及 Backend、Frontend 的契约使用方。"""

        level, modules, unmatched = test_changed.select_verification(
            self.config,
            ["backend/tests/contract/api_contract/test_cameras_openapi.py"],
        )

        self.assertEqual(level, "module")
        self.assertEqual(
            modules,
            ["api-contract", "backend-cameras", "frontend-cameras"],
        )
        self.assertEqual(unmatched, [])

    def test_APIContract各级命令都运行测试与生成物安全门禁(self) -> None:
        """无论选择器因规模提升到哪一级，都不能漏跑契约测试或专项脚本。"""

        required_fragments = {
            "pytest tests/contract/api_contract",
            "check-cameras-contracts.sh",
            "check-cameras-sensitive-data.sh",
        }
        for level in self.config["levels"]:
            commands = self.config["modules"]["api-contract"]["commands"][level]
            joined = "\n".join(commands)
            for fragment in required_fragments:
                self.assertIn(fragment, joined)

    def test_Cameras最终命令按风险逐层增加新目录(self) -> None:
        """02g 后 Cameras 不再执行 legacy 或公共 API Contract 目录。"""

        commands = self.config["modules"]["backend-cameras"]["commands"]
        unit = "\n".join(commands["unit"])
        module = "\n".join(commands["module"])
        integration = "\n".join(commands["integration"])

        self.assertIn("pytest tests/unit/cameras", unit)
        self.assertNotIn("tests/module/cameras", unit)
        self.assertIn("tests/unit/cameras tests/module/cameras", module)
        self.assertNotIn("tests/integration/cameras", module)
        self.assertIn(
            "tests/unit/cameras tests/module/cameras tests/integration/cameras",
            integration,
        )
        for joined in (unit, module, integration):
            self.assertNotIn("tests/modules/cameras", joined)
            self.assertNotIn("tests/contract/api_contract", joined)

    def test_StreamGateway变更继续影响Cameras且使用最终命令(self) -> None:
        """Stream Gateway 源码变化仍需带上已迁移的 Cameras 测试。"""

        level, modules, unmatched = test_changed.select_verification(
            self.config,
            ["backend/src/app/modules/stream_gateway/api/dependencies.py"],
        )

        self.assertEqual(level, "module")
        self.assertEqual(modules, ["backend-cameras", "backend-stream-gateway"])
        self.assertEqual(unmatched, [])
        cameras_command = "\n".join(
            self.config["modules"]["backend-cameras"]["commands"][level]
        )
        self.assertIn("tests/unit/cameras tests/module/cameras", cameras_command)
        self.assertNotIn("tests/modules/cameras", cameras_command)

    def test_StreamGateway测试目录按层级选择并继续影响Cameras(self) -> None:
        """三类测试使用各自风险级别，跨模块影响使低层测试至少运行到 module。"""

        cases = [
            ("backend/tests/unit/stream_gateway/test_ports.py", "module"),
            (
                "backend/tests/contract/stream_gateway/test_mediamtx_openapi.py",
                "module",
            ),
            (
                "backend/tests/integration/stream_gateway/test_mediamtx_adapter.py",
                "integration",
            ),
        ]
        for path, expected_level in cases:
            with self.subTest(path=path):
                level, modules, unmatched = test_changed.select_verification(
                    self.config,
                    [path],
                )

                self.assertEqual(level, expected_level)
                self.assertEqual(modules, ["backend-cameras", "backend-stream-gateway"])
                self.assertEqual(unmatched, [])

    def test_StreamGateway外部边界变化选择Integration(self) -> None:
        """HTTP Adapter、真实门禁与共享 MediaMTX 协议都必须运行 integration。"""

        cases = [
            (
                "backend/src/app/modules/stream_gateway/services/mediamtx.py",
                ["backend-cameras", "backend-stream-gateway"],
            ),
            (
                "backend/scripts/check_mediamtx_contract.py",
                ["backend-cameras", "backend-stream-gateway"],
            ),
            (
                "backend/scripts/check_mediamtx_adapter.py",
                ["backend-cameras", "backend-stream-gateway"],
            ),
            (
                "contracts/mediamtx-openapi.json",
                [
                    "backend-cameras",
                    "backend-stream-gateway",
                    "frontend-cameras",
                    "frontend-video",
                ],
            ),
        ]
        for path, expected_modules in cases:
            with self.subTest(path=path):
                level, modules, unmatched = test_changed.select_verification(
                    self.config,
                    [path],
                )

                self.assertEqual(level, "integration")
                self.assertEqual(modules, expected_modules)
                self.assertEqual(unmatched, [])

    def test_StreamGateway最终命令按风险增加目录和真实门禁(self) -> None:
        """unit、contract、Adapter 与真实 MediaMTX 门禁按风险逐步加入。"""

        commands = self.config["modules"]["backend-stream-gateway"]["commands"]
        unit = "\n".join(commands["unit"])
        module = "\n".join(commands["module"])
        integration = "\n".join(commands["integration"])

        self.assertIn("pytest tests/unit/stream_gateway", unit)
        self.assertNotIn("tests/contract/stream_gateway", unit)
        self.assertIn(
            "pytest tests/unit/stream_gateway tests/contract/stream_gateway",
            module,
        )
        self.assertNotIn("tests/integration/stream_gateway", module)
        self.assertIn(
            "pytest tests/unit/stream_gateway tests/contract/stream_gateway "
            "tests/integration/stream_gateway",
            integration,
        )
        self.assertIn("scripts/check_mediamtx_contract.py", integration)
        self.assertIn("scripts/check_mediamtx_adapter.py", integration)

        for level in self.config["levels"]:
            joined = "\n".join(commands[level])
            self.assertNotIn("tests/modules/stream_gateway", joined)
            self.assertNotIn("tests/module/stream_gateway", joined)

    def test_FrontendCameras未迁移时继续运行共置测试(self) -> None:
        """API Contract 影响 Frontend 时，任务 04 前必须运行当前存在的共置测试。"""

        for level in self.config["levels"]:
            commands = self.config["modules"]["frontend-cameras"]["commands"][level]
            joined = "\n".join(commands)
            self.assertIn("src/features/cameras", joined)
            self.assertIn("src/mocks/cameras", joined)
            self.assertIn("src/routes/_app/cameras", joined)
            self.assertIn("src/test/cameras-contract-security.test.ts", joined)
            self.assertNotIn("tests/unit/cameras", joined)

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
            ["backend/tests/legacy/cameras/test_legacy.py"],
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
