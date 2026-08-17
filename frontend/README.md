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

Generated files such as `src/routeTree.gen.ts` are excluded from linting. Type
checking remains part of `pnpm build` and is not replaced by ESLint.

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
