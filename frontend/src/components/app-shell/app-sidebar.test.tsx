import {
  createRootRoute,
  createRoute,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";

import { AppSidebar } from "@/components/app-shell/app-sidebar";
import { SidebarRouteSync } from "@/components/app-shell/sidebar-route-sync";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { setViewportWidth } from "@/test/browser-mocks";
import { createTestRouter } from "@/test/render-router";

function SidebarStateProbe() {
  const { isMobile, open, openMobile } = useSidebar();

  return (
    <output
      aria-label="侧边栏状态"
      data-mobile={isMobile}
      data-open={open}
      data-open-mobile={openMobile}
    />
  );
}

function TestShell() {
  return (
    <TooltipProvider>
      <SidebarProvider>
        <SidebarRouteSync />
        <SidebarStateProbe />
        <AppSidebar />
        <SidebarInset>
          <SidebarTrigger aria-label="打开主导航" />
          <Outlet />
        </SidebarInset>
      </SidebarProvider>
    </TooltipProvider>
  );
}

function createSidebarRouter(initialPath: string) {
  const rootRoute = createRootRoute({ component: TestShell });
  const camerasRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/cameras",
    component: Outlet,
  });
  const cameraDetailRoute = createRoute({
    getParentRoute: () => camerasRoute,
    path: "$cameraId",
  });
  const tasksRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/tasks",
    component: Outlet,
  });
  const taskDetailRoute = createRoute({
    getParentRoute: () => tasksRoute,
    path: "$taskId",
  });
  const routeTree = rootRoute.addChildren([
    camerasRoute.addChildren([cameraDetailRoute]),
    tasksRoute.addChildren([taskDetailRoute]),
  ]);

  return createTestRouter({ routeTree }, { initialEntries: [initialPath] });
}

function renderAt(initialPath: string, width = 1024) {
  setViewportWidth(width);
  const router = createSidebarRouter(initialPath);

  render(<RouterProvider router={router} />);

  return router;
}

test.each([
  ["/cameras", "摄像头", "检测任务"],
  ["/cameras/camera-1", "摄像头", "检测任务"],
  ["/tasks", "检测任务", "摄像头"],
  ["/tasks/task-1", "检测任务", "摄像头"],
])(
  "在 %s 路径正确标记主导航活动项",
  async (path, activeLabel, inactiveLabel) => {
    renderAt(path);

    const activeLink = (await screen.findByText(activeLabel)).closest("a");
    const inactiveLink = screen.getByText(inactiveLabel).closest("a");

    expect(activeLink).toHaveAttribute("aria-current", "page");
    expect(activeLink).toHaveAttribute("data-active");
    expect(inactiveLink).not.toHaveAttribute("aria-current");
    expect(inactiveLink).not.toHaveAttribute("data-active");
  },
);

test("选择菜单链接后关闭移动端 Sheet", async () => {
  const user = userEvent.setup();
  const router = renderAt("/tasks", 500);

  await user.click(await screen.findByRole("button", { name: "打开主导航" }));
  await user.click(await screen.findByRole("link", { name: "摄像头" }));

  await waitFor(() => {
    expect(router.state.location.pathname).toBe("/cameras");
    expect(
      screen.queryByRole("link", { name: "摄像头" }),
    ).not.toBeInTheDocument();
  });
});

test("浏览器后退和前进时都关闭移动端 Sheet", async () => {
  const user = userEvent.setup();
  const router = renderAt("/tasks", 500);

  await act(async () => {
    await router.navigate({ to: "/cameras" });
  });
  await user.click(await screen.findByRole("button", { name: "打开主导航" }));

  expect(
    await screen.findByRole("link", { name: "检测任务" }),
  ).toBeInTheDocument();

  act(() => {
    router.history.back();
  });

  await waitFor(() => {
    expect(router.state.location.pathname).toBe("/tasks");
    expect(
      screen.queryByRole("link", { name: "检测任务" }),
    ).not.toBeInTheDocument();
  });

  await user.click(await screen.findByRole("button", { name: "打开主导航" }));
  expect(
    await screen.findByRole("link", { name: "摄像头" }),
  ).toBeInTheDocument();

  act(() => {
    router.history.forward();
  });

  await waitFor(() => {
    expect(router.state.location.pathname).toBe("/cameras");
    expect(
      screen.queryByRole("link", { name: "摄像头" }),
    ).not.toBeInTheDocument();
  });
});

test("从 767px 切换到 768px 时关闭 openMobile 且不修改桌面 open", async () => {
  const user = userEvent.setup();

  renderAt("/tasks", 767);

  const state = await screen.findByRole("status", { name: "侧边栏状态" });
  await user.click(screen.getByRole("button", { name: "打开主导航" }));

  expect(state).toHaveAttribute("data-mobile", "true");
  expect(state).toHaveAttribute("data-open", "true");
  expect(state).toHaveAttribute("data-open-mobile", "true");

  act(() => setViewportWidth(768));

  await waitFor(() => {
    expect(state).toHaveAttribute("data-mobile", "false");
    expect(state).toHaveAttribute("data-open-mobile", "false");
  });
  expect(state).toHaveAttribute("data-open", "true");

  act(() => setViewportWidth(767));

  await waitFor(() => {
    expect(state).toHaveAttribute("data-mobile", "true");
    expect(state).toHaveAttribute("data-open-mobile", "false");
  });
});

test("可通过键盘操作桌面折叠按钮", async () => {
  const user = userEvent.setup();
  renderAt("/cameras");

  const trigger = await screen.findByLabelText("折叠侧边栏");

  // jsdom 不解析 Tailwind 的 md 媒体查询；移除移动端隐藏类来模拟桌面可见态。
  trigger.classList.remove("hidden");
  trigger.focus();
  await user.keyboard("{Enter}");

  expect(screen.getByLabelText("展开侧边栏")).toHaveAttribute(
    "aria-expanded",
    "false",
  );
});

test("桌面 Sidebar 折叠后悬停菜单项会打开 Tooltip", async () => {
  const user = userEvent.setup();
  renderAt("/cameras");

  await user.keyboard("{Control>}b{/Control}");
  const camerasLink = await screen.findByRole("link", { name: "摄像头" });

  await user.hover(camerasLink);

  await waitFor(() => expect(camerasLink).toHaveAttribute("data-popup-open"));
});
