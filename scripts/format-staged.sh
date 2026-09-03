#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"

declare -a staged_paths=()
declare -a backend_paths=()
declare -a frontend_paths=()
declare -a formatted_paths=()
declare -A worktree_was_clean=()
declare -A formatted_files=()

# 使用 NUL 分隔文件名，避免空格等常见特殊字符让路径被错误拆分。
mapfile -d '' staged_paths < <(
  git -C "${repo_root}" diff --cached --name-only --diff-filter=ACMR -z
)

for path in "${staged_paths[@]}"; do
  case "${path}" in
    backend/*.py)
      backend_paths+=("${path}")
      ;;
    frontend/*)
      frontend_paths+=("${path}")
      ;;
  esac
done

if (( ${#backend_paths[@]} == 0 && ${#frontend_paths[@]} == 0 )); then
  exit 0
fi

if (( ${#backend_paths[@]} > 0 )) && ! command -v uv >/dev/null 2>&1; then
  echo "提交失败：格式化 Backend 暂存文件需要 uv，请先安装 uv。" >&2
  exit 1
fi

if (( ${#frontend_paths[@]} > 0 )) && ! command -v pnpm >/dev/null 2>&1; then
  echo "提交失败：格式化 Frontend 暂存文件需要 pnpm，请先安装 pnpm。" >&2
  exit 1
fi

temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/sop-vision-format-staged.XXXXXX")"
trap 'rm -rf -- "${temp_dir}"' EXIT

format_backend_file() {
  local path="$1"
  local temp_path="${temp_dir}/${path}"

  mkdir -p -- "$(dirname -- "${temp_path}")"
  git -C "${repo_root}" show ":${path}" >"${temp_path}"

  # 显式指定项目配置，确保临时文件仍使用仓库的 Python 版本和 100 字符行宽。
  # --frozen 禁止提交钩子顺带更新 uv.lock；依赖未安装时仍会严格按现有 lock 安装。
  uv run --frozen --project "${repo_root}/backend" ruff format \
    --config "${repo_root}/backend/pyproject.toml" \
    --quiet \
    "${temp_path}"

  formatted_paths+=("${path}")
  formatted_files["${path}"]="${temp_path}"
}

format_frontend_file() {
  local path="$1"
  local file_info
  local temp_path="${temp_dir}/${path}"

  # 先让 Prettier 根据真实路径判断忽略规则和解析器，生成文件不会被钩子改写。
  file_info="$(
    pnpm --dir "${repo_root}/frontend" exec prettier \
      --file-info "${repo_root}/${path}" \
      --ignore-path "${repo_root}/frontend/.prettierignore"
  )"
  if [[ "${file_info}" == *'"ignored": true'* || "${file_info}" == *'"inferredParser": null'* ]]; then
    return
  fi

  mkdir -p -- "$(dirname -- "${temp_path}")"
  git -C "${repo_root}" show ":${path}" >"${temp_path}"

  # 配置文件显式传入，避免 Prettier 从临时目录向上查找时漏掉项目配置。
  pnpm --dir "${repo_root}/frontend" exec prettier \
    --config "${repo_root}/frontend/prettier.config.js" \
    --log-level silent \
    --write \
    "${temp_path}"

  formatted_paths+=("${path}")
  formatted_files["${path}"]="${temp_path}"
}

# 先记录工作区是否还有未暂存改动。后续只同步完全暂存的文件，防止误提交额外内容。
for path in "${backend_paths[@]}" "${frontend_paths[@]}"; do
  if git -C "${repo_root}" diff --quiet -- "${path}"; then
    worktree_was_clean["${path}"]=1
  else
    worktree_was_clean["${path}"]=0
  fi
done

# 所有文件先在临时目录完成格式化。任一格式化器失败时，Git index 仍保持原样。
for path in "${backend_paths[@]}"; do
  format_backend_file "${path}"
done
for path in "${frontend_paths[@]}"; do
  format_frontend_file "${path}"
done

for path in "${formatted_paths[@]}"; do
  temp_path="${formatted_files[${path}]}"
  staged_blob="$(git -C "${repo_root}" rev-parse ":${path}")"
  formatted_blob="$(git -C "${repo_root}" hash-object -w -- "${temp_path}")"

  if [[ "${staged_blob}" == "${formatted_blob}" ]]; then
    continue
  fi

  index_entry="$(git -C "${repo_root}" ls-files --stage -- "${path}")"
  file_mode="${index_entry%% *}"
  git -C "${repo_root}" update-index --cacheinfo "${file_mode}" "${formatted_blob}" "${path}"

  if [[ "${worktree_was_clean[${path}]}" == 1 ]]; then
    # 文件没有未暂存改动时，同步工作区，避免提交后立刻出现一份反向格式差异。
    cp -- "${temp_path}" "${repo_root}/${path}"
    echo "已格式化并暂存：${path}"
  else
    # 部分暂存文件只更新 index；覆盖工作区会丢失开发者尚未暂存的内容。
    echo "已格式化暂存内容：${path}（工作区含未暂存改动，未覆盖工作区文件）"
  fi
done
