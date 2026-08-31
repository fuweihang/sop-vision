// @ts-check

import js from "@eslint/js";
import { defineConfig, globalIgnores } from "eslint/config";
import reactHooks from "eslint-plugin-react-hooks";
import { reactRefresh } from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

const sourceFiles = ["src/**/*.{ts,tsx}"];

export default defineConfig(
  globalIgnores([
    "coverage/**",
    "dist/**",
    "src/generated/openapi.ts",
    "src/routeTree.gen.ts",
    "src/vendor/mediamtx/reader.js",
  ]),
  {
    files: ["**/*.{js,mjs,cjs,ts,tsx}"],
    extends: [js.configs.recommended, tseslint.configs.recommended],
  },
  {
    files: ["*.config.{js,ts}"],
    languageOptions: {
      globals: globals.node,
    },
  },
  {
    files: ["scripts/**/*.mjs"],
    languageOptions: {
      globals: globals.node,
    },
  },
  {
    files: sourceFiles,
    extends: [tseslint.configs.recommendedTypeChecked],
    languageOptions: {
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },
  {
    files: sourceFiles,
    extends: [reactHooks.configs.flat.recommended],
  },
  {
    files: sourceFiles,
    extends: [reactRefresh.configs.vite()],
    rules: {
      "react-refresh/only-export-components": [
        "warn",
        {
          allowConstantExport: true,
        },
      ],
    },
  },
  {
    files: ["src/components/ui/*.tsx"],
    rules: {
      "react-refresh/only-export-components": [
        "warn",
        {
          allowConstantExport: true,
          allowExportNames: ["buttonVariants", "badgeVariants", "useSidebar"],
        },
      ],
    },
  },
  {
    files: ["src/routes/**/*.tsx"],
    rules: {
      "react-refresh/only-export-components": "off",
    },
  },
);
