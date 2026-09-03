#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"

if [[ "$(git -C "${repo_root}" rev-parse --show-toplevel)" != "${repo_root}" ]]; then
  echo "安装失败：脚本所在目录不是当前 Git 仓库根目录。" >&2
  exit 1
fi

current_hooks_path="$(git -C "${repo_root}" config --local --get core.hooksPath || true)"
if [[ -n "${current_hooks_path}" && "${current_hooks_path}" != ".githooks" ]]; then
  echo "安装失败：当前仓库已经使用 Git hooks 目录 ${current_hooks_path}。" >&2
  echo "请先合并已有钩子，再手动执行：git config --local core.hooksPath .githooks" >&2
  exit 1
fi

# core.hooksPath 使用仓库相对路径，移动或重新克隆仓库后配置仍然有效。
git -C "${repo_root}" config --local core.hooksPath .githooks
echo "Git hooks 已启用：提交时会自动格式化已暂存的 Backend 和 Frontend 文件。"
