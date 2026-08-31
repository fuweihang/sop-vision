import {
  createMemoryHistory,
  createRouter,
  RouterProvider,
  type AnyRoute,
  type RouterConstructorOptions,
} from "@tanstack/react-router";
import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";

import { Toaster } from "@/components/ui/sonner";
import {
  StreamSessionManager,
  StreamSessionProvider,
} from "@/features/video/stream-session";
import { FakeStreamSession } from "@/features/video/testing/fakes";
import { apiClient } from "@/lib/api-client";
import { queryClient } from "@/lib/query-client";
import { ThemeProvider } from "@/providers/theme-provider";
import { routeTree } from "@/routeTree.gen";

type TestHistoryOptions = {
  initialEntries: string[];
  initialIndex?: number;
};

type TestRouterOptions<TRouteTree extends AnyRoute> = RouterConstructorOptions<
  TRouteTree,
  "never",
  false,
  ReturnType<typeof createMemoryHistory>,
  Record<string, unknown>
>;

export function createTestRouter<TRouteTree extends AnyRoute>(
  routerOptions: TestRouterOptions<TRouteTree>,
  { initialEntries, initialIndex }: TestHistoryOptions,
) {
  const history = createMemoryHistory(
    initialIndex === undefined
      ? { initialEntries }
      : { initialEntries, initialIndex },
  );

  return createRouter<
    TRouteTree,
    "never",
    false,
    ReturnType<typeof createMemoryHistory>,
    Record<string, unknown>
  >({
    ...routerOptions,
    history,
  });
}

export function createAppTestRouter(
  historyOptions: TestHistoryOptions = { initialEntries: ["/cameras"] },
) {
  return createTestRouter(
    {
      routeTree,
      context: { apiClient, queryClient },
    },
    historyOptions,
  );
}

export type AppTestRouter = ReturnType<typeof createAppTestRouter>;

export function renderAppRoute(
  initialPath: string,
  configure?: (router: AppTestRouter) => void,
) {
  const router = createAppTestRouter({ initialEntries: [initialPath] });

  configure?.(router);
  const fakeStreamSessions: FakeStreamSession[] = [];
  const streamSessionManager = new StreamSessionManager(() => {
    const session = new FakeStreamSession();
    fakeStreamSessions.push(session);
    return session;
  });

  const renderResult = render(
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
      <QueryClientProvider client={queryClient}>
        <StreamSessionProvider manager={streamSessionManager}>
          <RouterProvider router={router} />
          <Toaster />
        </StreamSessionProvider>
      </QueryClientProvider>
    </ThemeProvider>,
  );

  return {
    ...renderResult,
    router,
    streamSessionManager,
    fakeStreamSessions,
  };
}
