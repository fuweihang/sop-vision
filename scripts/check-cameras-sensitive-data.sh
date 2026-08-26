#!/usr/bin/env bash

set -euo pipefail

repository_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

# 专项门禁故意不依赖 PostgreSQL 或 MediaMTX，使安全边界可以在完整测试之外快速复验。
cd "${repository_root}/backend"
uv run pytest -m sensitive_data

cd "${repository_root}/frontend"
pnpm test:sensitive-data
