# React + TypeScript + Vite

This frontend uses React, TypeScript, and Vite.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Linting

The project uses ESLint flat config with type-aware `typescript-eslint` rules,
the stable React Hooks recommendations, and Vite Fast Refresh checks.

```sh
pnpm lint
pnpm lint:fix
```

Generated files such as `src/routeTree.gen.ts` and `src/generated/openapi.ts`
are excluded from linting. Type checking remains part of `pnpm build` and is
not replaced by ESLint. Rebuild the OpenAPI operation types from the repository
contract with `pnpm api:generate`; never edit the generated file directly.

## Formatting

The project uses Prettier for deterministic code formatting. ESLint remains
responsible for code-quality and type-aware diagnostics.

```sh
pnpm format
pnpm format:check
```

VS Code workspace settings enable Prettier on save and run ESLint fixes on
explicit saves. `src/routeTree.gen.ts` and other generated output are excluded
from formatting.

## Cameras MSW 场景开发

Camera 后端业务切片尚未实现时，可以在 `.env.local` 中显式选择一个 MSW 场景，再运行
`pnpm dev`：

```dotenv
VITE_API_MOCK_SCENARIO=success
```

可选场景：

- `success`：七个 Cameras operation 全部成功。
- `empty-list`、`search-no-results`：两类不同的空列表语义。
- `nested-validation-error`：创建和更新返回嵌套字段 `422`。
- `camera-not-found`、`source-not-found`：Camera 或 Source 返回 `404`。
- `playback-not-available`：Playback 返回带 `Retry-After` 的 `409`。
- `playback-invalid-response`：Playback 返回 `502`。
- `dependency-unavailable`：数据库或媒体依赖返回 `503`。
- `initial-failure`：列表首次失败，重试成功。
- `background-refresh-failure`：列表首次成功，后续刷新失败。

Mock 只在 Vite 开发模式且变量非空时启动。场景名无效或请求没有对应 handler 时会直接报错，
不会回退到真实 Backend 或 MediaMTX。生产构建不会启动 Mock；`public` 中随构建复制的 Worker
脚本没有注册入口，因此保持静态、未激活状态。
