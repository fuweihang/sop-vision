import { defineConfig, mergeConfig } from "vitest/config";

import vitestConfig from "./vitest.config.ts";

/**
 * 敏感数据专项复用完整测试的 jsdom、setup 和严格 Mock 边界，只收窄测试文件集合。
 * 文件清单放在类型安全、可格式化的配置中，避免 package.json 脚本随着门禁扩展持续变长。
 */
export default mergeConfig(
  vitestConfig,
  defineConfig({
    test: {
      include: [
        "src/lib/api-client.test.ts",
        "src/lib/api-errors.test.ts",
        "src/mocks/cameras/fixtures.test.ts",
        "src/mocks/cameras/scenarios.test.ts",
        "src/test/cameras-contract-security.test.ts",
      ],
    },
  }),
);
