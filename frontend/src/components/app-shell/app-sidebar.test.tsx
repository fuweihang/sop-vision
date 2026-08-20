import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { AppSidebar } from "@/components/app-shell/app-sidebar";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";

function TestShell() {
  return (
    <TooltipProvider>
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset>
          <SidebarTrigger aria-label="打开主导航" />
          <Outlet />
        </SidebarInset>
      </SidebarProvider>
    </TooltipProvider>
  );
}

function createTestRouter(initialPath: string) {
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

  return createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [initialPath] }),
  });
}

function setViewport(width: number) {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: width,
  });
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn((query: string) => ({
      matches: query === "(max-width: 767px)" && width < 768,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

function renderAt(initialPath: string, width = 1024) {
  setViewport(width);
  const router = createTestRouter(initialPath);

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
