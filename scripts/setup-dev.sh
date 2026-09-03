#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"

with_services=false
install_hooks=true

show_help() {
  cat <<'EOF'
用法：./scripts/setup-dev.sh [选项]

初始化 SOP Vision 宿主机开发环境。默认创建缺失的本地配置、安装前后端依赖、
启用 Git hooks，并检查 Docker Compose 配置；不会启动服务或修改数据库。

选项：
  --with-services  启动 PostgreSQL、Redis、MediaMTX，并执行数据库迁移
  --skip-hooks     不安装当前仓库的 Git hooks
  -h, --help       显示帮助
EOF
}

fail() {
  echo "初始化失败：$1" >&2
  exit 1
}

require_command() {
  local command_name="$1"
  local install_hint="$2"

  if ! command -v "${command_name}" >/dev/null 2>&1; then
    fail "未找到 ${command_name}。${install_hint}"
  fi
}

copy_config_if_missing() {
  local source_path="$1"
  local target_path="$2"
  local display_path="${target_path#${repo_root}/}"

  if [[ -e "${target_path}" ]]; then
    echo "保留已有配置：${display_path}"
    return
  fi

  # 本地配置可能包含开发者自己的端口和凭据，重复执行时绝不能覆盖已有文件。
  cp -- "${source_path}" "${target_path}"
  echo "已创建配置：${display_path}"
}

for argument in "$@"; do
  case "${argument}" in
    --with-services)
      with_services=true
      ;;
    --skip-hooks)
      install_hooks=false
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      show_help >&2
      fail "不支持的参数 ${argument}"
      ;;
  esac
done

echo "[1/6] 检查开发工具"
require_command "uv" "请先安装 uv：https://docs.astral.sh/uv/getting-started/installation/"
require_command "node" "请安装 Node.js 24。"
require_command "docker" "请安装 Docker 和 Docker Compose。"

node_version="$(node --version)"
node_major="${node_version#v}"
node_major="${node_major%%.*}"
required_node_version="$(tr -d '[:space:]' <"${repo_root}/frontend/.node-version")"
required_node_major="${required_node_version%%.*}"
if [[ "${node_major}" != "${required_node_major}" ]]; then
  fail "当前 Node.js 为 ${node_version}，项目要求 Node.js ${required_node_major}。"
fi

if ! docker compose version >/dev/null 2>&1; then
  fail "当前 docker 命令不包含 Compose 插件。"
fi

if ! command -v pnpm >/dev/null 2>&1; then
  require_command "corepack" "Node.js 24 应提供 Corepack，请检查 Node.js 安装。"
  echo "未找到 pnpm，正在通过 Corepack 启用。"
  if ! corepack enable; then
    fail "Corepack 无法启用 pnpm，请检查 Node.js 安装目录权限后重试。"
  fi
  hash -r
fi

require_command "pnpm" "请通过 Corepack 安装 pnpm 11。"
pnpm_version="$(pnpm --version)"
pnpm_major="${pnpm_version%%.*}"
package_manager="$(
  node -e \
    'const fs = require("node:fs"); const data = JSON.parse(fs.readFileSync(process.argv[1])); process.stdout.write(data.packageManager);' \
    "${repo_root}/frontend/package.json"
)"
required_pnpm_version="${package_manager#pnpm@}"
required_pnpm_major="${required_pnpm_version%%.*}"
if [[ "${package_manager}" != pnpm@* || "${pnpm_major}" != "${required_pnpm_major}" ]]; then
  fail "当前 pnpm 为 ${pnpm_version}，项目要求 pnpm ${required_pnpm_major}。"
fi

echo "[2/6] 创建缺失的本地配置"
copy_config_if_missing "${repo_root}/.env.example" "${repo_root}/.env"
copy_config_if_missing \
  "${repo_root}/backend/.env.local.example" \
  "${repo_root}/backend/.env.local"
copy_config_if_missing \
  "${repo_root}/frontend/.env.local.example" \
  "${repo_root}/frontend/.env.local"

echo "[3/6] 安装 Backend 依赖"
uv sync --locked --project "${repo_root}/backend"

# .python-version 和 pyproject.toml 会让 uv 选择 Python 3.12；这里额外检查实际环境，
# 避免系统配置覆盖项目版本后，直到启动应用才暴露问题。
required_python_version="$(tr -d '[:space:]' <"${repo_root}/backend/.python-version")"
backend_python_version="$(
  uv run --frozen --project "${repo_root}/backend" \
    python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
)"
if [[ "${backend_python_version}" != "${required_python_version}" ]]; then
  fail "Backend 环境使用 Python ${backend_python_version}，项目要求 Python ${required_python_version}。"
fi

echo "[4/6] 安装 Frontend 依赖"
pnpm --dir "${repo_root}/frontend" install --frozen-lockfile

echo "[5/6] 配置开发工具"
if [[ "${install_hooks}" == true ]]; then
  "${repo_root}/scripts/install-git-hooks.sh"
else
  echo "已按参数跳过 Git hooks。"
fi

compose_files=(
  -f "${repo_root}/compose.yaml"
  -f "${repo_root}/compose.dev.yaml"
)

echo "[6/6] 检查 Docker Compose 配置"
docker compose "${compose_files[@]}" --env-file "${repo_root}/.env" config --quiet

if [[ "${with_services}" == true ]]; then
  echo "正在启动 PostgreSQL、Redis 和 MediaMTX。"
  docker compose "${compose_files[@]}" --env-file "${repo_root}/.env" \
    up -d --wait postgres redis mediamtx

  echo "正在执行 Backend 数据库迁移。"
  uv run --frozen --project "${repo_root}/backend" \
    --env-file "${repo_root}/backend/.env.local" \
    alembic upgrade head
fi

echo "开发环境初始化完成。"
if [[ "${with_services}" == false ]]; then
  echo "如需同时启动基础服务并迁移数据库，请运行：./scripts/setup-dev.sh --with-services"
fi
