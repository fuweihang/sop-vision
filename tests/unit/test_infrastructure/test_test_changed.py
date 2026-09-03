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

        paths = [
            "backend/tests/contract/api_contract/test_cameras_openapi.py",
            "frontend/tests/contract/api_contract/cameras-contract-security.test.ts",
        ]
        for path in paths:
            with self.subTest(path=path):
                level, modules, unmatched = test_changed.select_verification(
                    self.config,
                    [path],
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

    def test_FrontendShared最终命令逐层增加标准目录(self) -> None:
        """Shared 收尾后不再运行 src/lib，并按风险逐层增加标准目录。"""

        commands = self.config["modules"]["frontend-shared"]["commands"]
        unit = "\n".join(commands["unit"])
        module = "\n".join(commands["module"])
        integration = "\n".join(commands["integration"])

        self.assertIn("vitest run tests/unit/shared", unit)
        self.assertNotIn("tests/component/shared", unit)
        self.assertNotIn("tests/contract/shared", unit)
        self.assertIn("tests/component/shared", module)
        self.assertIn("tests/contract/shared", module)
        self.assertNotIn("tests/integration/shared", module)
        self.assertIn("tests/integration/shared", integration)
        for joined in (unit, module, integration):
            self.assertNotIn("src/lib", joined)

    def test_APIClient和Error变化从Shared模块测试开始验证(self) -> None:
        """公共 HTTP 边界变化不能只运行纯规则单元测试。"""

        shared_modules = [
            "frontend-cameras",
            "frontend-shared",
            "frontend-shell",
            "frontend-video",
        ]
        for path in (
            "frontend/src/lib/api-client.ts",
            "frontend/src/lib/api-errors.ts",
        ):
            with self.subTest(path=path):
                level, modules, unmatched = test_changed.select_verification(
                    self.config,
                    [path],
                )

                self.assertEqual(level, "module")
                self.assertEqual(modules, shared_modules)
                self.assertEqual(unmatched, [])

    def test_敏感数据配置变化运行现有APIContract专项脚本(self) -> None:
        """专项配置变化必须继续执行唯一的敏感数据检查入口。"""

        level, modules, unmatched = test_changed.select_verification(
            self.config,
            ["frontend/vitest.sensitive.config.ts"],
        )

        self.assertEqual(level, "integration")
        self.assertIn("api-contract", modules)
        self.assertEqual(unmatched, [])
        api_contract_commands = "\n".join(
            self.config["modules"]["api-contract"]["commands"][level]
        )
        self.assertIn("check-cameras-sensitive-data.sh", api_contract_commands)

    def test_FrontendShell最终命令逐层增加标准目录(self) -> None:
        """Shell 收尾后不再运行共置测试，并按风险逐层增加标准目录。"""

        commands = self.config["modules"]["frontend-shell"]["commands"]
        unit = "\n".join(commands["unit"])
        module = "\n".join(commands["module"])
        integration = "\n".join(commands["integration"])

        self.assertIn("vitest run tests/unit/app_shell", unit)
        self.assertNotIn("tests/component/app_shell", unit)
        self.assertIn(
            "tests/unit/app_shell tests/component/app_shell "
            "tests/contract/app_shell",
            module,
        )
        self.assertNotIn("tests/integration/app_shell", module)
        self.assertIn(
            "tests/unit/app_shell tests/component/app_shell "
            "tests/contract/app_shell tests/integration/app_shell",
            integration,
        )
        legacy_paths = [
            "src/components/app-shell",
            "src/components/page-state",
            "src/components/route-state",
            "src/routes",
        ]
        for joined in (unit, module, integration):
            for path in legacy_paths:
                self.assertNotIn(path, joined)

    def test_Shared和Shell四层标准目录按风险选择对应模块(self) -> None:
        """每个新目录必须有唯一模块，并从该层级开始执行测试。"""

        shared_modules = [
            "frontend-cameras",
            "frontend-shared",
            "frontend-shell",
            "frontend-video",
        ]
        cases = [
            ("frontend/tests/unit/shared/route-meta.test.ts", "module", shared_modules),
            (
                "frontend/tests/component/shared/button.test.tsx",
                "module",
                shared_modules,
            ),
            (
                "frontend/tests/contract/shared/api-client.test.ts",
                "module",
                shared_modules,
            ),
            (
                "frontend/tests/integration/shared/providers.test.tsx",
                "integration",
                shared_modules,
            ),
            (
                "frontend/tests/unit/app_shell/navigation.test.ts",
                "unit",
                ["frontend-shell"],
            ),
            (
                "frontend/tests/component/app_shell/header.test.tsx",
                "module",
                ["frontend-shell"],
            ),
            (
                "frontend/tests/contract/app_shell/routes.test.ts",
                "module",
                ["frontend-shell"],
            ),
            (
                "frontend/tests/integration/app_shell/layout.test.tsx",
                "integration",
                ["frontend-shell"],
            ),
        ]
        for path, expected_level, expected_modules in cases:
            with self.subTest(path=path):
                level, modules, unmatched = test_changed.select_verification(
                    self.config,
                    [path],
                )

                self.assertEqual(level, expected_level)
                self.assertEqual(modules, expected_modules)
                self.assertEqual(unmatched, [])

    def test_Frontend公共Setup和Support变化验证全部使用模块(self) -> None:
        """公共测试基础变化必须执行所有 Frontend 使用方的 integration 测试。"""

        paths = [
            "frontend/tests/setup.ts",
            "frontend/tests/support/browser-mocks.ts",
            "frontend/tests/support/media-browser-mocks.ts",
            "frontend/tests/support/render-router.tsx",
        ]
        for path in paths:
            with self.subTest(path=path):
                level, modules, unmatched = test_changed.select_verification(
                    self.config,
                    [path],
                )

                self.assertEqual(level, "integration")
                self.assertEqual(
                    modules,
                    [
                        "frontend-cameras",
                        "frontend-shared",
                        "frontend-shell",
                        "frontend-video",
                    ],
                )
                self.assertEqual(unmatched, [])

    def test_Video最终命令按风险逐层增加标准目录和Reader校验(self) -> None:
        """05d 后 Video 只运行标准目录，真实媒体源仍保持手工启动。"""

        commands = self.config["modules"]["frontend-video"]["commands"]
        unit = "\n".join(commands["unit"])
        module = "\n".join(commands["module"])
        integration = "\n".join(commands["integration"])

        self.assertIn("vitest run tests/unit/video", unit)
        self.assertNotIn("tests/component/video", unit)
        self.assertNotIn("tests/contract/video", unit)
        self.assertIn(
            "vitest run tests/unit/video tests/component/video tests/contract/video",
            module,
        )
        self.assertNotIn("tests/integration/video", module)
        self.assertIn(
            "vitest run tests/unit/video tests/component/video tests/contract/video "
            "tests/integration/video",
            integration,
        )
        self.assertNotIn("vendor:check", unit)
        self.assertNotIn("vendor:check", module)
        self.assertIn("pnpm vendor:check", integration)

        for joined in (unit, module, integration):
            self.assertNotIn("src/features/video", joined)
            self.assertNotIn("whep:test-source", joined)

    def test_FrontendCameras最终命令按风险逐层增加新目录(self) -> None:
        """04h 后 Cameras 只运行标准目录，不再执行共置测试或公共 Contract。"""

        commands = self.config["modules"]["frontend-cameras"]["commands"]
        unit = "\n".join(commands["unit"])
        module = "\n".join(commands["module"])
        integration = "\n".join(commands["integration"])

        self.assertIn("tests/unit/cameras", unit)
        self.assertNotIn("tests/component/cameras", unit)
        self.assertIn(
            "tests/unit/cameras tests/component/cameras tests/contract/cameras",
            module,
        )
        self.assertNotIn("tests/integration/cameras", module)
        self.assertIn(
            "tests/unit/cameras tests/component/cameras tests/contract/cameras "
            "tests/integration/cameras",
            integration,
        )

        legacy_paths = [
            "src/features/cameras",
            "src/mocks/cameras",
            "src/routes/_app/cameras",
            "src/test/cameras-contract-security.test.ts",
            "tests/contract/api_contract",
        ]
        for level, joined in (
            ("unit", unit),
            ("module", module),
            ("integration", integration),
        ):
            with self.subTest(level=level):
                for path in legacy_paths:
                    self.assertNotIn(path, joined)

    def test_Cameras路由变化同时选择Shell与Cameras集成测试(self) -> None:
        """业务路由既属于 App Shell 的路由树，也包含 Cameras 的页面流程。"""

        level, modules, unmatched = test_changed.select_verification(
            self.config,
            ["frontend/src/routes/_app/cameras/$cameraId.tsx"],
        )

        self.assertEqual(level, "integration")
        self.assertEqual(modules, ["frontend-cameras", "frontend-shell"])
        self.assertEqual(unmatched, [])

    def test_Shell入口和普通路由变化执行Shell集成测试(self) -> None:
        """应用入口、生成路由树和非 Cameras 路由都必须覆盖完整导航流程。"""

        paths = [
            "frontend/src/App.tsx",
            "frontend/src/routes/_app/tasks/index.tsx",
            "frontend/src/routeTree.gen.ts",
        ]
        for path in paths:
            with self.subTest(path=path):
                level, modules, unmatched = test_changed.select_verification(
                    self.config,
                    [path],
                )

                self.assertEqual(level, "integration")
                self.assertEqual(modules, ["frontend-shell"])
                self.assertEqual(unmatched, [])

    def test_Video变化继续使用Cameras最终命令(self) -> None:
        """Video 的既有影响关系必须调用 Cameras 标准目录，不能带回旧过滤路径。"""

        level, modules, unmatched = test_changed.select_verification(
            self.config,
            ["frontend/src/features/video/components/video-surface/video-surface.tsx"],
        )

        self.assertEqual(level, "module")
        self.assertEqual(modules, ["frontend-cameras", "frontend-video"])
        self.assertEqual(unmatched, [])
        cameras_command = "\n".join(
            self.config["modules"]["frontend-cameras"]["commands"][level]
        )
        self.assertIn(
            "tests/unit/cameras tests/component/cameras tests/contract/cameras",
            cameras_command,
        )
        self.assertNotIn("src/features/cameras", cameras_command)

    def test_Frontend四层标准目录按风险选择Cameras模块(self) -> None:
        """每个新目录必须选择唯一模块，并从最低有效层级开始验证。"""

        cases = [
            ("frontend/tests/unit/cameras/query-keys.test.ts", "unit"),
            ("frontend/tests/component/cameras/card.test.tsx", "module"),
            ("frontend/tests/contract/cameras/api.test.ts", "module"),
            ("frontend/tests/integration/cameras/routes.test.tsx", "integration"),
        ]
        for path, expected_level in cases:
            with self.subTest(path=path):
                level, modules, unmatched = test_changed.select_verification(
                    self.config,
                    [path],
                )

                self.assertEqual(level, expected_level)
                self.assertEqual(modules, ["frontend-cameras"])
                self.assertEqual(unmatched, [])

    def test_Video四层标准目录按风险选择Video及其影响模块(self) -> None:
        """Video 测试按目录定级，并继续验证依赖 Video 的 Cameras。"""

        cases = [
            # Video 会影响 Cameras，因此单元测试也至少提升到跨模块验证。
            ("frontend/tests/unit/video/geometry.test.ts", "module"),
            ("frontend/tests/component/video/controls.test.tsx", "module"),
            ("frontend/tests/contract/video/whep-session.test.ts", "module"),
            ("frontend/tests/integration/video/session.test.tsx", "integration"),
        ]
        for path, expected_level in cases:
            with self.subTest(path=path):
                level, modules, unmatched = test_changed.select_verification(
                    self.config,
                    [path],
                )

                self.assertEqual(level, expected_level)
                self.assertEqual(modules, ["frontend-cameras", "frontend-video"])
                self.assertEqual(unmatched, [])

    def test_Video专用Support选择Video和Cameras集成测试(self) -> None:
        """共享 Session Fake 变化必须覆盖 Video 及当前 Cameras 使用方。"""

        level, modules, unmatched = test_changed.select_verification(
            self.config,
            ["frontend/tests/support/video/fake-stream-session.ts"],
        )

        self.assertEqual(level, "integration")
        self.assertEqual(modules, ["frontend-cameras", "frontend-video"])
        self.assertEqual(unmatched, [])
        cameras_command = "\n".join(
            self.config["modules"]["frontend-cameras"]["commands"][level]
        )
        self.assertIn("tests/integration/cameras", cameras_command)

    def test_Cameras专用Support按Module级选择Cameras模块(self) -> None:
        """Session 渲染工具只服务 Cameras 组件测试，不应扩大到全部 Frontend 模块。"""

        level, modules, unmatched = test_changed.select_verification(
            self.config,
            ["frontend/tests/support/cameras/render-with-stream-session.tsx"],
        )

        self.assertEqual(level, "module")
        self.assertEqual(modules, ["frontend-cameras"])
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

    def test_Frontend旧测试工具路径重新出现时不能被忽略(self) -> None:
        """删除临时豁免后，生产源码目录不能重新混入测试基础文件。"""

        with patch.object(test_changed.Path, "exists", return_value=True):
            level, modules, unmatched = test_changed.select_verification(
                self.config,
                ["frontend/src/test/setup.ts"],
            )

        self.assertEqual(level, "unit")
        self.assertEqual(modules, [])
        self.assertEqual(unmatched, ["frontend/src/test/setup.ts"])

    def test_允许删除未登记的旧测试工具路径(self) -> None:
        """迁移删除源码旁旧工具时，不应要求为已经消失的文件保留影响规则。"""

        with patch.object(test_changed.Path, "exists", return_value=False):
            level, modules, unmatched = test_changed.select_verification(
                self.config,
                ["frontend/src/test/setup.ts"],
            )

        self.assertEqual(level, "unit")
        self.assertEqual(modules, [])
        self.assertEqual(unmatched, [])

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
