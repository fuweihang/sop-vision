import { defineConfig } from "vitest/config";

import vitestConfig from "./vitest.config.ts";

/**
 * 敏感数据专项复用完整测试的 jsdom、setup 和严格 Mock 边界，只替换测试文件集合。
 * 这里不能使用 mergeConfig：Vite 会拼接 include 数组，导致基础配置里的全部测试也被执行。
 */
export default defineConfig({
  ...vitestConfig,
  test: {
    ...vitestConfig.test,
    include: [
      "tests/contract/shared/api-client.test.ts",
      "tests/contract/shared/api-errors.test.ts",
      "tests/unit/cameras/fixtures.test.ts",
      "tests/integration/cameras/scenarios.test.ts",
      "tests/contract/api_contract/cameras-contract-security.test.ts",
    ],
  },
});
