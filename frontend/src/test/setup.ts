import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach, vi } from "vitest";

import { queryClient } from "@/lib/query-client";
import { mockServer } from "@/mocks/node";
import { resetBrowserState } from "@/test/browser-mocks";
import { restoreMediaBrowserMocks } from "@/test/media-browser-mocks";

beforeAll(() => {
  // 未匹配 handler 必须让测试立即失败；MSW 不得把请求透传到真实 Backend/MediaMTX。
  mockServer.listen({ onUnhandledRequest: "error" });
});

beforeEach(resetBrowserState);

afterEach(() => {
  cleanup();
  restoreMediaBrowserMocks();
  // 使用 fake timers 的用例即使中途失败，也不能让后续路由刷新和操作栏计时继续跑在假时钟上。
  vi.useRealTimers();
  mockServer.resetHandlers();
  // CameraDetail 含凭据；清空共享内存缓存也避免查询状态和敏感 Fixture 跨测试泄漏。
  queryClient.clear();
  resetBrowserState();
});

afterAll(() => {
  mockServer.close();
});
