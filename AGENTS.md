# 仓库指南

## 项目结构与模块组织

`backend/src/app/` 是 FastAPI 控制面：应用级入口位于 `api/`，配置、HTTP 和数据库基础位于 `core/`，业务代码位于 `modules/<domain>/`。当前业务模块为 `cameras` 和 `stream_gateway`；Cameras 内部继续按 `api/`、`application/`、`domain/`、`persistence/` 分层。Alembic revision 位于 `backend/migrations/`，生成 OpenAPI 和发布门禁位于 `backend/scripts/`。

`frontend/src/` 是 React 应用：文件路由位于 `routes/`，业务能力位于 `features/`，应用外壳和共享组件位于 `components/`，共享客户端与工具位于 `lib/`，全局 Provider 位于 `providers/`。架构和 UI 规则记录在 `docs/`；修改共享 UI 前先阅读 `docs/design-system/`。`contracts/openapi.json`、`frontend/src/generated/openapi.ts` 和 `frontend/src/routeTree.gen.ts` 都是生成文件，不得手工编辑。

测试不再镜像源码或与前端源码共置。Backend 使用 `backend/tests/<layer>/<module>/`，Frontend 使用 `frontend/tests/<layer>/<module>/`，测试工具使用仓库级 `tests/unit/test_infrastructure/`。公共 Fixture、Builder、Fake 和 Setup 放在对应测试根的 `support/` 中。

## 构建、测试与开发命令

- 完整容器环境：`cp .env.example .env && docker compose -f compose.yaml -f compose.dev.yaml up -d --build --wait`；停止时使用相同 `-f` 参数执行 `down`。
- Backend：在 `backend/` 中运行 `uv sync --locked`，复制 `.env.local.example` 为 `.env.local`，再使用 `uv run --env-file .env.local python -m app.server --host 127.0.0.1 --port 3001 --reload`。数据库变更先执行 `uv run --env-file .env.local alembic upgrade head`。
- Frontend：使用 Node 24 和 pnpm 11；在 `frontend/` 中运行 `corepack enable`、`pnpm install --frozen-lockfile` 和 `pnpm dev`。`pnpm build` 同时执行 TypeScript 检查和 Vite 生产构建。
- 日常交付只运行 `./scripts/verify-changed.sh`，由脚本选择测试范围并压缩日志。只有排查失败时才直接运行 Pytest 或 Vitest；独立质量命令见 Backend/Frontend README。

## 编码风格与命名约定

Python 面向 3.12，使用四个空格、完整类型提示、100 字符行宽和 Ruff；模块及函数使用 `snake_case`，类使用 `PascalCase`。TypeScript 使用严格类型检查、两个空格、分号、双引号、ESLint 和 Prettier；避免类型断言掩盖数据边界问题。React 组件和类型使用 `PascalCase`，函数使用 `camelCase`，组件文件使用 kebab-case，从 `frontend/src/` 导入时使用 `@/` 别名。代码中的注释、异常、日志和测试描述默认使用简体中文，并解释非直观实现的原因。

## 测试

当生产代码的行为发生变化时，请使用 `test-policy` 技能。

测试必须遵循 `test-impact.json` 登记的“层级 + 模块”路径，不得自行设置测试位置或测试命令。

在交付前，请运行：

```bash
./scripts/verify-changed.sh
```

脚本根据风险和规模在 unit、module、integration 之间升级，并将完整输出写入临时日志。默认不运行全量测试；失败时先使用 `rg` 检索脚本给出的日志路径，只读取定位问题所需的片段。

## Git 与 Pull Request

创建 Git 提交时使用 `git-commit` skill；创建、准备或更新 Pull Request 时使用 `pull-request` skill。不得提交 `.env`、密钥、凭据或本地运行数据。
