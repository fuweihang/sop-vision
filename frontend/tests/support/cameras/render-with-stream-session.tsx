import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";
import { type ReactNode, StrictMode } from "react";

import { TooltipProvider } from "@/components/ui/tooltip";
import {
  StreamSessionManager,
  StreamSessionProvider,
} from "@/features/video/stream-session";
import { FakeStreamSession } from "../video/fake-stream-session";

/**
 * Camera 组件测试只注入确定的 Session Fake 和 Tooltip 上下文，不复制 Router、Query 或 App Shell。
 * 需要验证路由组合的用例继续使用 renderAppRoute。
 */
export function renderWithStreamSession(
  ui: ReactNode,
  options?: Omit<RenderOptions, "wrapper"> & { strict?: boolean },
) {
  const { strict = false, ...renderOptions } = options ?? {};
  const fakeStreamSessions: FakeStreamSession[] = [];
  const acquiredWhepUrls: string[] = [];
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const streamSessionManager = new StreamSessionManager((whepUrl) => {
    acquiredWhepUrls.push(whepUrl);
    const session = new FakeStreamSession();
    fakeStreamSessions.push(session);
    return session;
  });
  function StreamSessionTestWrapper({ children }: { children: ReactNode }) {
    const content = (
      <QueryClientProvider client={queryClient}>
        <StreamSessionProvider manager={streamSessionManager}>
          <TooltipProvider>{children}</TooltipProvider>
        </StreamSessionProvider>
      </QueryClientProvider>
    );
    return strict ? <StrictMode>{content}</StrictMode> : content;
  }

  const result = render(ui, {
    ...renderOptions,
    wrapper: StreamSessionTestWrapper,
  });

  return {
    ...result,
    acquiredWhepUrls,
    fakeStreamSessions,
    queryClient,
    streamSessionManager,
  };
}
