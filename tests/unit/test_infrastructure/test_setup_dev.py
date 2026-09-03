from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class SetupDevScriptTests(unittest.TestCase):
    """使用伪造的外部工具验证初始化顺序，不安装依赖或启动真实容器。"""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary_directory.name)
        self.bin_directory = self.repository / "fake-bin"
        self.command_log = self.repository / "commands.log"
        self.bin_directory.mkdir()

        self._copy_project_file("scripts/setup-dev.sh")
        self._write_executable(
            "scripts/install-git-hooks.sh",
            """
            #!/usr/bin/env bash
            printf 'install-hooks\\n' >> "${SETUP_TEST_LOG:?}"
            """,
        )
        self._write(".env.example", "ROOT_ENV=example\n")
        self._write("backend/.env.local.example", "BACKEND_ENV=example\n")
        self._write("frontend/.env.local.example", "FRONTEND_ENV=example\n")
        self._write("backend/.python-version", "3.12\n")
        self._write("frontend/.node-version", "24\n")
        self._write("frontend/package.json", '{"packageManager":"pnpm@11.21.0"}\n')
        self._write("compose.yaml", "services: {}\n")
        self._write("compose.dev.yaml", "services: {}\n")
        self._install_fake_commands()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_默认初始化创建配置安装依赖但不启动服务(self) -> None:
        result = self._run("bash", "scripts/setup-dev.sh")

        self.assertIn("开发环境初始化完成", result.stdout)
        self.assertEqual("ROOT_ENV=example\n", self._read(".env"))
        self.assertEqual("BACKEND_ENV=example\n", self._read("backend/.env.local"))
        self.assertEqual("FRONTEND_ENV=example\n", self._read("frontend/.env.local"))

        command_log = self.command_log.read_text()
        self.assertIn("uv sync --locked --project", command_log)
        self.assertIn("pnpm --dir", command_log)
        self.assertIn("install-hooks", command_log)
        self.assertIn("docker compose", command_log)
        self.assertIn("config --quiet", command_log)
        self.assertNotIn("up -d --wait", command_log)
        self.assertNotIn("alembic upgrade head", command_log)

    def test_with_services_启动依赖并执行迁移(self) -> None:
        self._run("bash", "scripts/setup-dev.sh", "--with-services")

        command_log = self.command_log.read_text()
        self.assertIn("up -d --wait postgres redis mediamtx", command_log)
        self.assertIn("alembic upgrade head", command_log)

    def test_重复执行保留配置并可跳过_hooks(self) -> None:
        self._write(".env", "ROOT_ENV=custom\n")
        self._write("backend/.env.local", "BACKEND_ENV=custom\n")
        self._write("frontend/.env.local", "FRONTEND_ENV=custom\n")

        result = self._run("bash", "scripts/setup-dev.sh", "--skip-hooks")

        self.assertIn("保留已有配置：.env", result.stdout)
        self.assertIn("已按参数跳过 Git hooks", result.stdout)
        self.assertEqual("ROOT_ENV=custom\n", self._read(".env"))
        self.assertEqual("BACKEND_ENV=custom\n", self._read("backend/.env.local"))
        self.assertEqual("FRONTEND_ENV=custom\n", self._read("frontend/.env.local"))
        self.assertNotIn("install-hooks", self.command_log.read_text())

    def test_Node主版本不符时在修改文件前失败(self) -> None:
        self._write_executable(
            "fake-bin/node",
            """
            #!/usr/bin/env bash
            echo 'v22.0.0'
            """,
        )

        result = self._run("bash", "scripts/setup-dev.sh", expect_success=False)

        self.assertIn("项目要求 Node.js 24", result.stderr)
        self.assertFalse((self.repository / ".env").exists())

    def test_缺少pnpm时使用_corepack_启用(self) -> None:
        (self.bin_directory / "pnpm").rename(self.bin_directory / "pnpm-template")
        self._write_executable(
            "fake-bin/corepack",
            r"""
            #!/usr/bin/env bash
            printf 'corepack %s\n' "$*" >> "${SETUP_TEST_LOG:?}"
            mv -- "${0%/*}/pnpm-template" "${0%/*}/pnpm"
            """,
        )

        result = self._run("bash", "scripts/setup-dev.sh", "--skip-hooks")

        self.assertIn("正在通过 Corepack 启用", result.stdout)
        self.assertIn("corepack enable", self.command_log.read_text())

    def _install_fake_commands(self) -> None:
        self._write_executable(
            "fake-bin/uv",
            r"""
            #!/usr/bin/env bash
            printf 'uv %s\n' "$*" >> "${SETUP_TEST_LOG:?}"
            if [[ "$*" == *"python -c"* ]]; then
              echo '3.12'
            elif [[ "${1:-}" == "--version" ]]; then
              echo 'uv 1.0.0'
            fi
            """,
        )
        self._write_executable(
            "fake-bin/node",
            """
            #!/usr/bin/env bash
            if [[ "${1:-}" == "--version" ]]; then
              echo 'v24.0.0'
            else
              printf 'pnpm@11.21.0'
            fi
            """,
        )
        self._write_executable(
            "fake-bin/pnpm",
            r"""
            #!/usr/bin/env bash
            if [[ "${1:-}" == "--version" ]]; then
              echo '11.21.0'
            else
              printf 'pnpm %s\n' "$*" >> "${SETUP_TEST_LOG:?}"
            fi
            """,
        )
        self._write_executable(
            "fake-bin/docker",
            r"""
            #!/usr/bin/env bash
            if [[ "$*" == "compose version" ]]; then
              echo 'Docker Compose version v2.0.0'
            else
              printf 'docker %s\n' "$*" >> "${SETUP_TEST_LOG:?}"
            fi
            """,
        )

    def _copy_project_file(self, relative_path: str) -> None:
        destination = self.repository / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPOSITORY_ROOT / relative_path, destination)

    def _write(self, relative_path: str, content: str) -> None:
        path = self.repository / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def _write_executable(self, relative_path: str, content: str) -> None:
        path = self.repository / relative_path
        self._write(relative_path, textwrap.dedent(content).lstrip())
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def _read(self, relative_path: str) -> str:
        return (self.repository / relative_path).read_text()

    def _run(
        self,
        *command: str,
        expect_success: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PATH"] = f"{self.bin_directory}{os.pathsep}/usr/bin:/bin"
        environment["SETUP_TEST_LOG"] = str(self.command_log)
        result = subprocess.run(
            command,
            cwd=self.repository,
            env=environment,
            capture_output=True,
            text=True,
        )
        if expect_success and result.returncode != 0:
            self.fail(
                f"命令执行失败：{' '.join(command)}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )
        if not expect_success and result.returncode == 0:
            self.fail(f"命令应失败但成功：{' '.join(command)}")
        return result


if __name__ == "__main__":
    unittest.main()
