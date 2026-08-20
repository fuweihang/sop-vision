import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import { AppHeader } from "@/components/app-shell/app-header";
import { ThemeToggle } from "@/components/app-shell/theme-toggle";
import { SidebarProvider } from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/providers/theme-provider";
import { Route as CamerasRoute } from "@/routes/_app/cameras";
import { Route as TasksRoute } from "@/routes/_app/tasks";

const LONG_CAMERA_LABEL = "名称非常长且必须保持单行显示的生产线摄像头测试标签";

function TestShell() {
  return (
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
      <TooltipProvider>
        <SidebarProvider>
          <AppHeader />
          <Outlet />
        </SidebarProvider>
      </TooltipProvider>
    </ThemeProvider>
  );
}

function createHeaderRouter(initialPath: string) {
  const rootRoute = createRootRoute({ component: TestShell });
  const camerasRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/cameras",
    staticData: { breadcrumb: "摄像头" },
    component: Outlet,
  });
  const cameraDetailRoute = createRoute({
    getParentRoute: () => camerasRoute,
    path: "$cameraId",
    staticData: {
      breadcrumb: LONG_CAMERA_LABEL,
      back: {
        to: "/cameras",
        label: "返回摄像头列表",
      },
    },
  });
  const tasksRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/tasks",
    staticData: { breadcrumb: "检测任务" },
  });

  return createRouter({
    routeTree: rootRoute.addChildren([
      camerasRoute.addChildren([cameraDetailRoute]),
      tasksRoute,
    ]),
    history: createMemoryHistory({ initialEntries: [initialPath] }),
  });
}

function createDeepHeaderRouter() {
  const rootRoute = createRootRoute({ component: TestShell });
  const workspaceRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/workspace",
    staticData: { breadcrumb: "Workspace" },
    component: Outlet,
  });
  const camerasRoute = createRoute({
    getParentRoute: () => workspaceRoute,
    path: "cameras",
    staticData: { breadcrumb: "摄像头" },
    component: Outlet,
  });
  const cameraRoute = createRoute({
    getParentRoute: () => camerasRoute,
    path: "$cameraId",
    staticData: { breadcrumb: "Camera 42" },
    component: Outlet,
  });
  const settingsRoute = createRoute({
    getParentRoute: () => cameraRoute,
    path: "settings",
    staticData: { breadcrumb: "Settings" },
  });

  return createRouter({
    routeTree: rootRoute.addChildren([
      workspaceRoute.addChildren([
        camerasRoute.addChildren([cameraRoute.addChildren([settingsRoute])]),
      ]),
    ]),
    history: createMemoryHistory({
      initialEntries: ["/workspace/cameras/camera-42/settings"],
    }),
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

function renderHeaderAt(initialPath: string) {
  const router = createHeaderRouter(initialPath);

  render(<RouterProvider router={router} />);

  return router;
}

beforeEach(() => {
  setViewport(1024);
  localStorage.clear();
  document.documentElement.className = "";
});

test.each([
  [CamerasRoute, "摄像头"],
  [TasksRoute, "检测任务"],
])("列表路由声明 %s Breadcrumb", (route, label) => {
  expect(route.options.staticData?.breadcrumb).toBe(label);
});

test.each([
  ["/cameras", "摄像头"],
  ["/tasks", "检测任务"],
])("在 %s 渲染当前 Breadcrumb", async (path, label) => {
  renderHeaderAt(path);

  const breadcrumb = await screen.findByRole("navigation", {
    name: "breadcrumb",
  });
  const currentItem = within(breadcrumb).getByText(label);

  expect(currentItem).toHaveAttribute("aria-current", "page");
  expect(currentItem.closest("a")).toBeNull();
});

test("父 Breadcrumb 可点击且当前项不可点击", async () => {
  renderHeaderAt("/cameras/camera-42");

  const breadcrumb = await screen.findByRole("navigation", {
    name: "breadcrumb",
  });

  expect(
    within(breadcrumb).getByRole("link", { name: "摄像头" }),
  ).toHaveAttribute("href", "/cameras");
  expect(within(breadcrumb).getByText(LONG_CAMERA_LABEL)).toHaveAttribute(
    "aria-current",
    "page",
  );
});

test("仅在 back 元数据存在时显示指向明确父路由的返回链接", async () => {
  const { unmount } = render(
    <RouterProvider router={createHeaderRouter("/cameras")} />,
  );

  await screen.findByRole("navigation", { name: "breadcrumb" });
  expect(screen.queryByRole("link", { name: "返回摄像头列表" })).toBeNull();

  unmount();
  renderHeaderAt("/cameras/camera-42");

  expect(
    await screen.findByRole("link", { name: "返回摄像头列表" }),
  ).toHaveAttribute("href", "/cameras");
});

test("移动端 SidebarTrigger 保留在 Header leading 区", async () => {
  setViewport(500);
  renderHeaderAt("/cameras");

  expect(await screen.findByRole("button", { name: "打开主导航" })).toHaveClass(
    "md:hidden",
  );
});

test("Theme Toggle 使用 Ghost Icon Button 并按 resolvedTheme 切换 dark class", async () => {
  const user = userEvent.setup();

  render(
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
      <TooltipProvider>
        <ThemeToggle />
      </TooltipProvider>
    </ThemeProvider>,
  );

  const toggle = await screen.findByRole("button", {
    name: "切换为深色主题",
  });

  expect(toggle).toHaveClass("size-8", "hover:bg-muted");
  await user.click(toggle);

  await waitFor(() => {
    expect(document.documentElement).toHaveClass("dark");
    expect(
      screen.getByRole("button", { name: "切换为浅色主题" }),
    ).toBeInTheDocument();
  });
});

test("长 Breadcrumb 保持 Header 固定高度并截断而不换行", async () => {
  renderHeaderAt("/cameras/camera-42");

  const header = await screen.findByRole("banner");
  const breadcrumb = screen.getByRole("navigation", { name: "breadcrumb" });
  const list = breadcrumb.querySelector('[data-slot="breadcrumb-list"]');
  const currentItem = within(breadcrumb).getByText(LONG_CAMERA_LABEL);

  expect(header).toHaveClass("h-14");
  expect(list).toHaveClass(
    "flex-nowrap",
    "overflow-hidden",
    "whitespace-nowrap",
  );
  expect(currentItem).toHaveClass("truncate");
});

test("Breadcrumb 在 Header 中心列内居中", async () => {
  renderHeaderAt("/cameras");

  const breadcrumb = await screen.findByRole("navigation", {
    name: "breadcrumb",
  });
  const centerRegion = breadcrumb.closest('[data-slot="app-header-center"]');

  expect(centerRegion).toHaveClass(
    "flex",
    "justify-center",
    "justify-self-stretch",
  );
});

test("超过三层时压缩为第一项、Ellipsis 和当前项", async () => {
  render(<RouterProvider router={createDeepHeaderRouter()} />);

  const breadcrumb = await screen.findByRole("navigation", {
    name: "breadcrumb",
  });

  expect(
    within(breadcrumb).getByRole("link", { name: "Workspace" }),
  ).toBeInTheDocument();
  expect(
    breadcrumb.querySelector('[data-slot="breadcrumb-ellipsis"]'),
  ).toBeInTheDocument();
  expect(within(breadcrumb).getByText("Settings")).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(within(breadcrumb).queryByText("摄像头")).toBeNull();
  expect(within(breadcrumb).queryByText("Camera 42")).toBeNull();
});
