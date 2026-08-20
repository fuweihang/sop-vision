# Repository Guidelines

## Project Structure & Module Organization

`backend/src/app/` contains the FastAPI control plane. Keep shared configuration in `core/` and place domain code under `modules/<domain>/`, separating `api/`, `schemas/`, and `services/`. Backend tests live in `backend/tests/` and mirror the source hierarchy. `frontend/src/` contains the React application: file-based routes are in `routes/`, reusable primitives in `components/ui/`, shell components in `components/app-shell/`, and shared logic in `lib/`. Keep frontend tests beside their subjects as `*.test.ts` or `*.test.tsx`. Architecture, requirements, and UI rules belong in `docs/`; consult `docs/design-system/` before changing shared UI. Do not edit generated `frontend/src/routeTree.gen.ts` manually.

## Build, Test, and Development Commands

- `cp .env.example .env && docker compose up --build --wait` builds and starts the complete local stack.
- `docker compose config` validates Compose and environment interpolation; `docker compose down` stops the stack.
- In `backend/`, run `uv sync`, then `uv run --env-file ../.env uvicorn app.main:app --app-dir src --reload --port 3001` for local API development.
- In `frontend/`, use Node 24 and pnpm 11: `pnpm install`, `pnpm dev`, and `pnpm build` install, serve, and type-check/build the app.
- Run `uv run pytest`, `uv run ruff check .`, and `uv run ruff format --check .` in `backend/`; run `pnpm test`, `pnpm lint`, and `pnpm format:check` in `frontend/`.

## Coding Style & Naming Conventions

Python uses four spaces, a 100-character line limit, type hints, `snake_case` functions/modules, and `PascalCase` classes. Ruff enforces imports and modern Python 3.12 practices. TypeScript uses two spaces, semicolons, double quotes, strict type-aware ESLint rules, and Prettier. Use `PascalCase` for React components, `camelCase` for functions, kebab-case component filenames, and the `@/` alias for `frontend/src/` imports.

## Testing Guidelines

Pytest discovers `test_*.py`; Vitest uses jsdom and Testing Library. Add tests for behavior changes and regressions, mock external HTTP boundaries, and keep tests deterministic. Coverage has no enforced minimum, but inspect it with `uv run pytest --cov=app --cov-report=term-missing` or `pnpm test:coverage`.

## Commit & Pull Request Guidelines

Recent commits use an emoji plus Conventional Commit form, usually with a scope: `✨ feat(frontend): ...`, `♻️ refactor(docs): ...`, or `🔧 chore(vscode): ...`. Keep each commit focused. Pull requests should explain the change and validation performed, link relevant issues or design documents, and include screenshots for visible UI changes. Call out configuration, API, or architecture impacts explicitly; never commit `.env` or credentials.
