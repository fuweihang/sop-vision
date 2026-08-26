#!/usr/bin/env bash

set -euo pipefail

# 所有路径都从脚本位置解析，保证开发者从仓库任意目录调用时得到相同结果。
repository_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${repository_root}/backend"
uv run python scripts/export_openapi.py

cd "${repository_root}/frontend"
pnpm api:generate

cd "${repository_root}"
# porcelain 同时覆盖已跟踪修改和“生成物曾被提交删除、重建后变成 untracked”的情况；单独使用
# git diff 会漏掉后一种漂移。路径范围仍只包含两份生成物，不干扰调用者的其他业务修改。
contract_drift="$(
  git status --porcelain=v1 --untracked-files=all -- \
    contracts/openapi.json frontend/src/generated/openapi.ts
)"
if [[ -n "${contract_drift}" ]]; then
  git diff -- contracts/openapi.json frontend/src/generated/openapi.ts
  printf '%s\n' "${contract_drift}"
  echo "Cameras 契约生成物存在漂移，请提交上述重建结果。" >&2
  exit 1
fi
echo "Cameras OpenAPI 与 TypeScript 生成物无漂移。"
