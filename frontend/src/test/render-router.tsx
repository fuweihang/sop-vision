import {
  createMemoryHistory,
  createRouter,
  RouterProvider,
  type AnyRoute,
  type RouterConstructorOptions,
} from "@tanstack/react-router";
import { render } from "@testing-library/react";

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

  const renderResult = render(
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
      <RouterProvider router={router} />
    </ThemeProvider>,
  );

  return { ...renderResult, router };
}
