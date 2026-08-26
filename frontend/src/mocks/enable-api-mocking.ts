/**
 * 仅在开发构建且显式配置场景时加载 MSW Browser 包。
 *
 * 动态导入让生产构建移除 Mock 实现；等待 Worker 就绪后再渲染 React，避免首个请求抢跑到真实
 * Backend。测试环境使用 Node server，不经过本入口。
 */
export async function enableApiMocking() {
  const scenarioName = import.meta.env.VITE_API_MOCK_SCENARIO?.trim();
  if (
    !import.meta.env.DEV ||
    scenarioName === undefined ||
    scenarioName === ""
  ) {
    return;
  }

  const { startBrowserMocking } = await import("@/mocks/browser");
  await startBrowserMocking(scenarioName);
}
