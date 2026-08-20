import {
  createMemoryHistory,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import { apiClient } from "@/lib/api-client";
import { queryClient } from "@/lib/query-client";
import { routeTree } from "@/routeTree.gen";
import { ThemeProvider } from "@/providers/theme-provider";

function renderRoute(initialPath: string) {
  const router = createRouter({
    routeTree,
    context: { apiClient, queryClient },
    history: createMemoryHistory({ initialEntries: [initialPath] }),
  });

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
