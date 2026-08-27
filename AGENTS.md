# 仓库指南

## 项目结构与模块组织

`backend/src/app/` 包含 FastAPI 控制平面。共享配置应放在 `core/` 中，领域代码应放在 `modules/<domain>/` 下，并分别组织到 `api/`、`schemas/` 和 `services/` 中。后端测试位于 `backend/tests/`，其目录结构应与源代码保持一致。`frontend/src/` 包含 React 应用：基于文件的路由位于 `routes/`，可复用的基础组件位于 `components/ui/`，应用外壳组件位于 `components/app-shell/`，共享逻辑位于 `lib/`。前端测试应与被测对象放在一起，并命名为 `*.test.ts` 或 `*.test.tsx`。架构、需求和 UI 规则应记录在 `docs/` 中；修改共享 UI 前，请先查阅 `docs/design-system/`。不要手动编辑自动生成的 `frontend/src/routeTree.gen.ts`。

## 构建、测试与开发命令

- `cp .env.example .env && docker compose up --build --wait` 用于构建并启动完整的本地技术栈。
- `docker compose config` 用于验证 Compose 配置和环境变量插值；`docker compose down` 用于停止该技术栈。
- 在 `backend/` 中，先运行 `uv sync`，再运行 `uv run --env-file ../.env uvicorn app.main:app --app-dir src --reload --port 3001` 进行本地 API 开发。
- 在 `frontend/` 中使用 Node 24 和 pnpm 11：通过 `pnpm install`、`pnpm dev` 和 `pnpm build` 分别安装依赖、启动开发服务以及执行类型检查并构建应用。
- 在 `backend/` 中常规运行 `uv run pytest`；如果测试依赖配置在 `backend/.env.local` 中的环境变量（尤其是 `TEST_DATABASE_URL`），必须运行 `uv run --env-file .env.local pytest`，否则相关 PostgreSQL 测试会被跳过。后端静态检查使用 `uv run ruff check .` 和 `uv run ruff format --check .`；在 `frontend/` 中运行 `pnpm test`、`pnpm lint` 和 `pnpm format:check`。

## 编码风格与命名约定

Python 使用四个空格缩进、每行最多 100 个字符和类型提示；函数及模块采用 `snake_case`，类采用 `PascalCase`。Ruff 用于强制执行导入规范和现代 Python 3.12 实践。TypeScript 使用两个空格缩进、分号、双引号、严格且支持类型感知的 ESLint 规则以及 Prettier。React 组件采用 `PascalCase`，函数采用 `camelCase`，组件文件名采用 kebab-case；从 `frontend/src/` 导入模块时使用 `@/` 别名。

## 测试指南

Pytest 会发现 `test_*.py` 文件；Vitest 使用 jsdom 和 Testing Library。应为行为变更和回归问题添加测试，对外部 HTTP 边界进行模拟，并确保测试结果具有确定性。目前不强制要求最低覆盖率，但可通过 `uv run pytest --cov=app --cov-report=term-missing` 或 `pnpm test:coverage` 检查测试覆盖率。

## 提交与拉取请求指南

近期提交采用表情符号加 Conventional Commits 的格式，并且通常包含作用域，例如：`✨ feat(frontend): ...`、`♻️ refactor(docs): ...` 或 `🔧 chore(vscode): ...`。每个提交都应聚焦于一项变更。拉取请求应说明所做的变更和执行的验证，关联相关 Issue 或设计文档，并为可见的 UI 变更附上截图。应明确说明对配置、API 或架构的影响；绝不要提交 `.env` 文件或凭据。
