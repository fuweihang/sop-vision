import { setupServer } from "msw/node";

/**
 * 不注册默认 handler：每个测试必须显式选择场景。
 *
 * 这样遗漏场景不会意外命中一个“总是成功”的全局 Mock；配合 setup 中的严格未处理策略，
 * 任何新增网络边界都会先以测试失败暴露。
 */
export const mockServer = setupServer();
