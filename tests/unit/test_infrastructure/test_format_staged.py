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


class FormatStagedHookTests(unittest.TestCase):
    """在隔离 Git 仓库中验证钩子，避免测试修改开发者当前工作区和暂存区。"""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary_directory.name)
        self.bin_directory = self.repository / "fake-bin"
        self.bin_directory.mkdir()

        self._run("git", "init", "--quiet")
        self._run("git", "config", "user.name", "测试用户")
        self._run("git", "config", "user.email", "test@example.com")

        self._copy_project_file("scripts/format-staged.sh")
        self._copy_project_file("scripts/install-git-hooks.sh")
        self._copy_project_file(".githooks/pre-commit")
        self._write("backend/pyproject.toml", "[tool.ruff]\nline-length = 100\n")
        self._write("frontend/prettier.config.js", "export default {};\n")
        self._write(
            "frontend/.prettierignore",
            "src/routeTree.gen.ts\nsrc/generated/openapi.ts\n",
        )
        self._install_fake_formatters()

        self._run("git", "add", ".")
        self._run("git", "commit", "--quiet", "-m", "初始化测试仓库")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_格式化前后端暂存文件并同步干净工作区(self) -> None:
        self._write("backend/example.py", "value=1\n")
        self._write("frontend/src/example.ts", "const value=1\n")
        self._run("git", "add", "backend/example.py", "frontend/src/example.ts")

        result = self._run("bash", "scripts/format-staged.sh")

        self.assertIn("已格式化并暂存：backend/example.py", result.stdout)
        self.assertIn("已格式化并暂存：frontend/src/example.ts", result.stdout)
        self.assertEqual("value = 1\n", self._index_content("backend/example.py"))
        self.assertEqual("const value = 1;\n", self._index_content("frontend/src/example.ts"))
        self.assertEqual("value = 1\n", self._read("backend/example.py"))
        self.assertEqual("const value = 1;\n", self._read("frontend/src/example.ts"))

    def test_部分暂存文件只更新索引并保留工作区改动(self) -> None:
        path = "frontend/src/partial.ts"
        self._write(path, "const value = 0;\n")
        self._run("git", "add", path)
        self._run("git", "commit", "--quiet", "-m", "添加基线文件")

        self._write(path, "const value=1\n")
        self._run("git", "add", path)
        self._write(path, "const value=1\nconst local=2\n")

        result = self._run("bash", "scripts/format-staged.sh")

        self.assertIn("工作区含未暂存改动", result.stdout)
        self.assertEqual("const value = 1;\n", self._index_content(path))
        self.assertEqual("const value=1\nconst local=2\n", self._read(path))

    def test_遵守_prettierignore_且不修改生成文件(self) -> None:
        path = "frontend/src/routeTree.gen.ts"
        self._write(path, "const generated=1\n")
        self._run("git", "add", path)

        self._run("bash", "scripts/format-staged.sh")

        self.assertEqual("const generated=1\n", self._index_content(path))
        self.assertEqual("const generated=1\n", self._read(path))

    def test_安装后_git_commit_会自动调用钩子(self) -> None:
        path = "backend/committed.py"
        self._write(path, "value=1\n")
        self._run("git", "add", path)

        self._run("bash", "scripts/install-git-hooks.sh")
        self._run("git", "commit", "--quiet", "-m", "验证提交钩子")

        self.assertEqual(".githooks\n", self._run("git", "config", "core.hooksPath").stdout)
        self.assertEqual("value = 1\n", self._run("git", "show", f"HEAD:{path}").stdout)

    def _install_fake_formatters(self) -> None:
        """伪造格式化器，只测试钩子的文件选择和 Git index 操作，不依赖本机工具版本。"""
        self._write_executable(
            "fake-bin/uv",
            r"""
            #!/usr/bin/env python3
            import pathlib
            import sys

            path = pathlib.Path(sys.argv[-1])
            path.write_text(path.read_text().replace("value=1", "value = 1"))
            """,
        )
        self._write_executable(
            "fake-bin/pnpm",
            r"""
            #!/usr/bin/env python3
            import json
            import pathlib
            import sys

            if "--file-info" in sys.argv:
                path = sys.argv[sys.argv.index("--file-info") + 1]
                ignored = path.endswith("src/routeTree.gen.ts") or path.endswith(
                    "src/generated/openapi.ts"
                )
                payload = {
                    "ignored": ignored,
                    "inferredParser": None if ignored else "typescript",
                }
                print(json.dumps(payload))
                raise SystemExit(0)

            path = pathlib.Path(sys.argv[-1])
            content = path.read_text().replace("value=1", "value = 1")
            if content.rstrip().startswith("const ") and not content.rstrip().endswith(";"):
                content = content.rstrip() + ";\n"
            path.write_text(content)
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

    def _index_content(self, relative_path: str) -> str:
        return self._run("git", "show", f":{relative_path}").stdout

    def _run(self, *command: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PATH"] = f"{self.bin_directory}{os.pathsep}{environment['PATH']}"
        result = subprocess.run(
            command,
            cwd=self.repository,
            env=environment,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            self.fail(
                f"命令执行失败：{' '.join(command)}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )
        return result


if __name__ == "__main__":
    unittest.main()
