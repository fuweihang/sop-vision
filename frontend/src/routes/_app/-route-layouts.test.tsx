import {
  createMemoryHistory,
  createRouter,
  notFound,
  RouterProvider,
} from "@tanstack/react-router";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import { apiClient } from "@/lib/api-client";
import { queryClient } from "@/lib/query-client";
import { routeTree } from "@/routeTree.gen";
import { ThemeProvider } from "@/providers/theme-provider";

function createTestRouter(initialPath: string) {
  return createRouter({
    routeTree,
    context: { apiClient, queryClient },
    history: createMemoryHistory({ initialEntries: [initialPath] }),
  });
}

type TestRouter = ReturnType<typeof createTestRouter>;

function renderRoute(
  initialPath: string,
  configure?: (router: TestRouter) => void,
) {
  const router = createTestRouter(initialPath);

  configure?.(router);

  render(
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
      <RouterProvider router={router} />
    </ThemeProvider>,
  );

  return router;
}

beforeEach(() => {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 1024,
  });
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

test.each([
  ["/cameras", "摄像头"],
  ["/cameras/camera-42", "camera-42"],
  ["/tasks", "检测任务"],
  ["/tasks/task-42", "task-42"],
])("可直接进入 %s 并只渲染一个页面主标题", async (path, title) => {
  renderRoute(path);

  const pageHeading = await screen.findByRole("heading", {
    level: 1,
    name: title,
  });
  const mainContent = document.getElementById("main-content");

  expect(pageHeading).toBeInTheDocument();
  expect(pageHeading).toHaveAttribute("data-route-focus");
  expect(pageHeading).toHaveAttribute("tabindex", "-1");
  expect(mainContent).toHaveAttribute("id", "main-content");
  expect(mainContent).toHaveAttribute("tabindex", "-1");
  expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  expect(
    screen.getByRole("heading", { level: 2, name: "路由骨架" }),
  ).toBeInTheDocument();
});

test("pathname 改变后将焦点移到新页面标题", async () => {
  const user = userEvent.setup();

  renderRoute("/cameras");

  const mainNavigation = await screen.findByRole("navigation", {
    name: "主菜单",
  });
  await user.click(
    within(mainNavigation).getByRole("link", { name: "检测任务" }),
  );

  const pageHeading = await screen.findByRole("heading", {
    level: 1,
    name: "检测任务",
  });
  await waitFor(() => expect(pageHeading).toHaveFocus());
});

test("仅 search params 改变时保留当前焦点", async () => {
  const router = renderRoute("/cameras");
  const themeToggle = await screen.findByRole("button", {
    name: "切换为深色主题",
  });

  themeToggle.focus();

  await act(async () => {
    await router.navigate({
      to: "/cameras",
      search: { filter: "connected" },
    });
  });

  expect(router.state.location.search).toEqual({ filter: "connected" });
  expect(themeToggle).toHaveFocus();
});

test("Skip Link 首个获得键盘焦点并将焦点交给主内容", async () => {
  const user = userEvent.setup();

  renderRoute("/cameras");
  await screen.findByRole("heading", { level: 1, name: "摄像头" });

  const skipLink = screen.getByRole("link", { name: "跳到主要内容" });
  const mainContent = document.getElementById("main-content");

  expect(skipLink).toHaveAttribute("href", "#main-content");
  expect(skipLink).toHaveClass("sr-only", "focus-visible:not-sr-only");

  await user.tab();
  expect(skipLink).toHaveFocus();

  await user.keyboard("{Enter}");
  expect(mainContent).toHaveFocus();
});

test.each([
  ["/cameras/camera-42", "摄像头", "camera-42", "返回摄像头列表", "/cameras"],
  ["/tasks/task-42", "检测任务", "task-42", "返回检测任务列表", "/tasks"],
])(
  "%s 显示父级与动态 Breadcrumb，并返回固定父列表",
  async (path, parentLabel, detailLabel, backLabel, parentPath) => {
    const user = userEvent.setup();
    const router = renderRoute(path);
    const breadcrumb = await screen.findByRole("navigation", {
      name: "breadcrumb",
    });

    expect(
      within(breadcrumb).getByRole("link", { name: parentLabel }),
    ).toHaveAttribute("href", parentPath);
    expect(within(breadcrumb).getByText(detailLabel)).toHaveAttribute(
      "aria-current",
      "page",
    );

    const backLink = screen.getByRole("link", { name: backLabel });
    expect(backLink).toHaveAttribute("href", parentPath);
    await user.click(backLink);

    expect(router.state.location.pathname).toBe(parentPath);
  },
);

test.each([
  ["/cameras/camera-42", "摄像头"],
  ["/tasks/task-42", "检测任务"],
])("详情路由 %s 保持父菜单激活", async (path, activeLabel) => {
  renderRoute(path);

  const mainNavigation = await screen.findByRole("navigation", {
    name: "主菜单",
  });

  expect(
    within(mainNavigation).getByRole("link", { name: activeLabel }),
  ).toHaveAttribute("aria-current", "page");
});

test.each([
  {
    path: "/cameras",
    routeId: "/_app/cameras/",
    pendingLabel: "正在加载摄像头列表",
    heading: "摄像头",
  },
  {
    path: "/cameras/camera-42",
    routeId: "/_app/cameras/$cameraId",
    pendingLabel: "正在加载摄像头详情",
    heading: "camera-42",
  },
  {
    path: "/tasks",
    routeId: "/_app/tasks/",
    pendingLabel: "正在加载检测任务列表",
    heading: "检测任务",
  },
  {
    path: "/tasks/task-42",
    routeId: "/_app/tasks/$taskId",
    pendingLabel: "正在加载检测任务详情",
    heading: "task-42",
  },
] as const)("$path Pending 保留 Shell 并提供可访问状态", async (testCase) => {
  let finishLoading = () => {};
  const loading = new Promise<void>((resolve) => {
    finishLoading = resolve;
  });
  let restoreRoute = () => {};

  try {
    renderRoute(testCase.path, (router) => {
      const targetRoute = router.routesById[testCase.routeId];
      const originalLoader = targetRoute.options.loader;
      const originalPendingMs = targetRoute.options.pendingMs;
      const originalPendingMinMs = targetRoute.options.pendingMinMs;

      targetRoute.options.loader = () => loading;
      targetRoute.options.pendingMs = 0;
      targetRoute.options.pendingMinMs = 0;
      restoreRoute = () => {
        if (originalLoader === undefined) {
          delete targetRoute.options.loader;
        } else {
          targetRoute.options.loader = originalLoader;
        }
        if (originalPendingMs === undefined) {
          delete targetRoute.options.pendingMs;
        } else {
          targetRoute.options.pendingMs = originalPendingMs;
        }
        if (originalPendingMinMs === undefined) {
          delete targetRoute.options.pendingMinMs;
        } else {
          targetRoute.options.pendingMinMs = originalPendingMinMs;
        }
      };
    });

    expect(
      await screen.findByRole("status", { name: testCase.pendingLabel }),
    ).toHaveAttribute("aria-busy", "true");
    expect(
      screen.getByRole("navigation", { name: "主菜单" }),
    ).toBeInTheDocument();
    expect(document.querySelectorAll('[data-slot="app-header"]')).toHaveLength(
      1,
    );

    act(() => finishLoading());
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: testCase.heading,
      }),
    ).toBeInTheDocument();
  } finally {
    finishLoading();
    restoreRoute();
  }
});

test("Cameras 子路由失败时保留 Shell，并可通过 invalidate 重试", async () => {
  const user = userEvent.setup();
  const consoleWarn = vi.spyOn(console, "warn").mockImplementation(() => {});
  let shouldFail = true;
  let restoreRoute = () => {};

  try {
    const router = renderRoute("/cameras/camera-42", (testRouter) => {
      const cameraRoute = testRouter.routesById["/_app/cameras/$cameraId"];
      const originalLoader = cameraRoute.options.loader;

      cameraRoute.options.loader = () => {
        if (shouldFail) {
          throw new Error("secret-token=must-not-be-rendered");
        }
      };
      restoreRoute = () => {
        if (originalLoader === undefined) {
          delete cameraRoute.options.loader;
        } else {
          cameraRoute.options.loader = originalLoader;
        }
      };
    });
    const invalidate = vi.spyOn(router, "invalidate");

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "无法加载摄像头内容",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: "主菜单" }),
    ).toBeInTheDocument();
    expect(document.querySelectorAll('[data-slot="app-header"]')).toHaveLength(
      1,
    );
    expect(screen.queryByText(/secret-token/)).not.toBeInTheDocument();
    expect(
      screen
        .getAllByRole("link", { name: "返回摄像头列表" })
        .some((link) => link.getAttribute("href") === "/cameras"),
    ).toBe(true);

    shouldFail = false;
    await user.click(screen.getByRole("button", { name: "重试" }));

    expect(invalidate).toHaveBeenCalledTimes(1);
    expect(
      await screen.findByRole("heading", { level: 1, name: "camera-42" }),
    ).toBeInTheDocument();
  } finally {
    restoreRoute();
    consoleWarn.mockRestore();
  }
});

test("Tasks 实体不存在时保留 Shell 并返回 Tasks", async () => {
  const consoleWarn = vi.spyOn(console, "warn").mockImplementation(() => {});
  let restoreRoute = () => {};

  try {
    renderRoute("/tasks/missing-task", (router) => {
      const taskRoute = router.routesById["/_app/tasks/$taskId"];
      const originalLoader = taskRoute.options.loader;

      taskRoute.options.loader = () => {
        notFound({ throw: true });
      };
      restoreRoute = () => {
        if (originalLoader === undefined) {
          delete taskRoute.options.loader;
        } else {
          taskRoute.options.loader = originalLoader;
        }
      };
    });

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "未找到检测任务",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: "主菜单" }),
    ).toBeInTheDocument();
    expect(document.querySelectorAll('[data-slot="app-header"]')).toHaveLength(
      1,
    );
    expect(
      screen
        .getAllByRole("link", { name: "返回检测任务列表" })
        .some((link) => link.getAttribute("href") === "/tasks"),
    ).toBe(true);
  } finally {
    restoreRoute();
    consoleWarn.mockRestore();
  }
});

test("未知 URL 显示全局 Not Found 而不是空白页面", async () => {
  renderRoute("/route-that-does-not-exist");

  expect(
    await screen.findByRole("heading", { level: 1, name: "页面不存在" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "返回首页" })).toHaveAttribute(
    "href",
    "/",
  );
});
