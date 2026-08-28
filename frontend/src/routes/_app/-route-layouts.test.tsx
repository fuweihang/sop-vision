import { notFound } from "@tanstack/react-router";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { CAMERA_FIXTURE_IDS } from "@/mocks/cameras/fixtures";
import { createCamerasMswScenario } from "@/mocks/cameras/scenarios";
import { mockServer } from "@/mocks/node";
import { renderAppRoute, type AppTestRouter } from "@/test/render-router";
import { setViewportWidth } from "@/test/browser-mocks";

const CAMERA_DETAIL_PATH = `/cameras/${CAMERA_FIXTURE_IDS.primaryCamera}`;

function renderRoute(
  initialPath: string,
  configure?: (router: AppTestRouter) => void,
) {
  // Camera 详情现在有真实 loader；Shell 测试提供确定的成功响应，业务错误由详情路由专测覆盖。
  mockServer.use(...createCamerasMswScenario("success"));
  return renderAppRoute(initialPath, configure).router;
}

test("根路径重定向到摄像头列表并渲染 Shell", async () => {
  const router = renderRoute("/");

  expect(
    await screen.findByRole("heading", { level: 1, name: "摄像头" }),
  ).toBeInTheDocument();
  expect(router.state.location.pathname).toBe("/cameras");
  expect(
    screen.getByRole("navigation", { name: "主菜单" }),
  ).toBeInTheDocument();
});

test.each([
  ["true", "expanded", "折叠侧边栏"],
  ["false", "collapsed", "展开侧边栏"],
])(
  "sidebar_state=%s 决定桌面 Sidebar 初始状态",
  async (cookieValue, expectedState, triggerLabel) => {
    document.cookie = `sidebar_state=${cookieValue}; path=/`;
    renderRoute("/cameras");

    await screen.findByRole("heading", { level: 1, name: "摄像头" });

    expect(
      document.querySelector('[data-slot="sidebar"][data-state]'),
    ).toHaveAttribute("data-state", expectedState);
    expect(screen.getByRole("button", { name: triggerLabel })).toHaveAttribute(
      "aria-expanded",
      cookieValue,
    );
  },
);

test.each([
  ["Control", "{Control>}b{/Control}"],
  ["Meta", "{Meta>}b{/Meta}"],
])("%s+B 切换桌面 Sidebar 并持久化状态", async (_modifier, shortcut) => {
  const user = userEvent.setup();
  renderRoute("/cameras");

  await screen.findByRole("heading", { level: 1, name: "摄像头" });
  await user.keyboard(shortcut);

  expect(
    document.querySelector('[data-slot="sidebar"][data-state]'),
  ).toHaveAttribute("data-state", "collapsed");
  expect(document.cookie).toContain("sidebar_state=false");
});

test("767px 渲染移动 Sheet，768px 渲染桌面 Sidebar", async () => {
  const user = userEvent.setup();
  setViewportWidth(767);
  const mobileRender = renderAppRoute("/cameras");

  await screen.findByRole("heading", { level: 1, name: "摄像头" });
  expect(screen.queryByRole("navigation", { name: "主菜单" })).toBeNull();

  await user.click(screen.getByRole("button", { name: "打开主导航" }));
  expect(await screen.findByRole("dialog", { name: "主导航" })).toHaveAttribute(
    "data-mobile",
    "true",
  );

  mobileRender.unmount();
  setViewportWidth(768);
  renderRoute("/cameras");

  expect(
    await screen.findByRole("navigation", { name: "主菜单" }),
  ).toBeInTheDocument();
  expect(screen.queryByRole("dialog", { name: "主导航" })).toBeNull();
  expect(
    document.querySelector('[data-slot="sidebar"][data-state]'),
  ).toBeInTheDocument();
});

test.each([
  ["/cameras", "摄像头"],
  [CAMERA_DETAIL_PATH, "洗手区 01"],
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
  if (path === CAMERA_DETAIL_PATH) {
    expect(
      screen.getByRole("heading", { level: 2, name: "连接信息" }),
    ).toBeInTheDocument();
  } else {
    expect(
      screen.getByRole("heading", { level: 2, name: "路由骨架" }),
    ).toBeInTheDocument();
  }
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
  [CAMERA_DETAIL_PATH, "摄像头", "洗手区 01", "返回摄像头列表", "/cameras"],
  ["/tasks/task-42", "检测任务", "task-42", "返回检测任务列表", "/tasks"],
])(
  "%s 显示父级与动态 Breadcrumb，并返回固定父列表",
  async (path, parentLabel, detailLabel, backLabel, parentPath) => {
    const user = userEvent.setup();
    const router = renderRoute(path);
    const breadcrumb = await screen.findByRole("navigation", {
      name: "面包屑导航",
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
  [CAMERA_DETAIL_PATH, "摄像头"],
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
    path: CAMERA_DETAIL_PATH,
    routeId: "/_app/cameras/$cameraId",
    pendingLabel: "正在加载摄像头详情",
    heading: "洗手区 01",
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
    const router = renderRoute(CAMERA_DETAIL_PATH, (testRouter) => {
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
      await screen.findByRole("heading", { level: 1, name: "洗手区 01" }),
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
