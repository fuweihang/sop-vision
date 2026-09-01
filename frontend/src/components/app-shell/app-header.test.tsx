import {
  createRootRoute,
  createRoute,
  Link,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";

import { AppHeader } from "@/components/app-shell/app-header";
import { ThemeToggle } from "@/components/app-shell/theme-toggle";
import { SidebarProvider } from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/providers/theme-provider";
import { getLoaderDataLabelOrParam } from "@/lib/route-meta";
import { Route as CamerasRoute } from "@/routes/_app/cameras/route";
import { Route as TasksRoute } from "@/routes/_app/tasks/route";
import { setViewportWidth } from "@/test/browser-mocks";
import { createTestRouter } from "@/test/render-router";

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
        label: "返回摄像头列表",
        renderLink: (props) => <Link to="/cameras" {...props} />,
      },
    },
  });
  const tasksRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/tasks",
    staticData: { breadcrumb: "检测任务" },
  });

  return createTestRouter(
    {
      routeTree: rootRoute.addChildren([
        camerasRoute.addChildren([cameraDetailRoute]),
        tasksRoute,
      ]),
    },
    { initialEntries: [initialPath] },
  );
}

function createDeepHeaderRouter() {
  const rootRoute = createRootRoute({ component: TestShell });
  const workspaceRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/workspace",
    staticData: { breadcrumb: "工作区" },
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
    staticData: { breadcrumb: "摄像头 42" },
    component: Outlet,
  });
  const settingsRoute = createRoute({
    getParentRoute: () => cameraRoute,
    path: "settings",
    staticData: { breadcrumb: "设置" },
  });

  return createTestRouter(
    {
      routeTree: rootRoute.addChildren([
        workspaceRoute.addChildren([
          camerasRoute.addChildren([cameraRoute.addChildren([settingsRoute])]),
        ]),
      ]),
    },
    {
      initialEntries: ["/workspace/cameras/camera-42/settings"],
    },
  );
}

function createDynamicHeaderRouter() {
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
    loader: () => ({ name: "总装线入口摄像头" }),
    staticData: {
      breadcrumb: {
        label: (match) =>
          getLoaderDataLabelOrParam(
            match,
            (loaderData) =>
              typeof loaderData === "object" &&
              loaderData !== null &&
              "name" in loaderData &&
              typeof loaderData.name === "string"
                ? loaderData.name
                : undefined,
            "cameraId",
          ) ?? "摄像头详情",
      },
    },
  });

  return createTestRouter(
    {
      routeTree: rootRoute.addChildren([
        camerasRoute.addChildren([cameraDetailRoute]),
      ]),
    },
    { initialEntries: ["/cameras/camera-42"] },
  );
}

function createParameterizedHeaderRouter() {
  const rootRoute = createRootRoute({ component: TestShell });
  const tasksRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/tasks",
    staticData: { breadcrumb: "项目列表" },
    component: Outlet,
  });
  const taskRoute = createRoute({
    getParentRoute: () => tasksRoute,
    path: "$taskId",
    staticData: {
      breadcrumb: {
        label: "项目",
        renderLink: (props) => (
          <Link
            to="/tasks/$taskId"
            params={{ taskId: "line camera" }}
            {...props}
          />
        ),
      },
    },
    component: Outlet,
  });
  const detailsRoute = createRoute({
    getParentRoute: () => taskRoute,
    path: "details",
    staticData: {
      breadcrumb: "详情",
      back: {
        label: "返回项目",
        renderLink: (props) => (
          <Link
            to="/tasks/$taskId"
            params={{ taskId: "line camera" }}
            {...props}
          />
        ),
      },
    },
  });

  return createTestRouter(
    {
      routeTree: rootRoute.addChildren([
        tasksRoute.addChildren([taskRoute.addChildren([detailsRoute])]),
      ]),
    },
    { initialEntries: ["/tasks/current/details"] },
  );
}

function renderHeaderAt(initialPath: string) {
  const router = createHeaderRouter(initialPath);

  render(<RouterProvider router={router} />);

  return router;
}

test.each([
  { route: CamerasRoute, label: "摄像头" },
  { route: TasksRoute, label: "检测任务" },
])("$label 列表路由声明 Breadcrumb", ({ route, label }) => {
  const breadcrumb = route.options.staticData?.breadcrumb;
  const actualLabel =
    typeof breadcrumb === "string" ? breadcrumb : breadcrumb?.label;

  expect(actualLabel).toBe(label);
});

test.each([
  ["/cameras", "摄像头"],
  ["/tasks", "检测任务"],
])("在 %s 渲染当前 Breadcrumb", async (path, label) => {
  renderHeaderAt(path);

  const breadcrumb = await screen.findByRole("navigation", {
    name: "面包屑导航",
  });
  const currentItem = within(breadcrumb).getByText(label);

  expect(currentItem).toHaveAttribute("aria-current", "page");
  expect(currentItem.closest("a")).toBeNull();
});

test("父 Breadcrumb 可点击且当前项不可点击", async () => {
  renderHeaderAt("/cameras/camera-42");

  const breadcrumb = await screen.findByRole("navigation", {
    name: "面包屑导航",
  });

  expect(
    within(breadcrumb).getByRole("link", { name: "摄像头" }),
  ).toHaveAttribute("href", "/cameras");
  expect(within(breadcrumb).getByText(LONG_CAMERA_LABEL)).toHaveAttribute(
    "aria-current",
    "page",
  );
});

test("详情 Breadcrumb 优先显示 loader 返回的动态名称", async () => {
  render(<RouterProvider router={createDynamicHeaderRouter()} />);

  const breadcrumb = await screen.findByRole("navigation", {
    name: "面包屑导航",
  });

  expect(within(breadcrumb).getByText("总装线入口摄像头")).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(within(breadcrumb).queryByText("camera-42")).toBeNull();
});

test("Breadcrumb 不设置 title 以禁用浏览器原生悬停提示", async () => {
  renderHeaderAt("/cameras/camera-42");

  const breadcrumb = await screen.findByRole("navigation", {
    name: "面包屑导航",
  });
  const parentItem = within(breadcrumb).getByRole("link", { name: "摄像头" });
  const currentItem = within(breadcrumb).getByText(LONG_CAMERA_LABEL);

  expect(parentItem).not.toHaveAttribute("title");
  expect(currentItem).not.toHaveAttribute("title");
});

test("仅在 back 元数据存在时显示指向明确父路由的返回链接", async () => {
  const { unmount } = render(
    <RouterProvider router={createHeaderRouter("/cameras")} />,
  );

  await screen.findByRole("navigation", { name: "面包屑导航" });
  expect(screen.queryByRole("link", { name: "返回摄像头列表" })).toBeNull();

  unmount();
  renderHeaderAt("/cameras/camera-42");

  const backLink = await screen.findByRole("link", {
    name: "返回摄像头列表",
  });

  expect(backLink).toHaveAttribute("href", "/cameras");
  expect(backLink).not.toHaveAttribute("role", "button");
  expect(backLink).not.toHaveAttribute("type", "button");
  expect(backLink).not.toHaveAttribute("data-slot", "tooltip-trigger");
});

test("动态目标由 Router 替换相似参数名并编码参数值", async () => {
  render(<RouterProvider router={createParameterizedHeaderRouter()} />);

  const breadcrumb = await screen.findByRole("navigation", {
    name: "面包屑导航",
  });
  const expectedHref = "/tasks/line%20camera";

  expect(
    within(breadcrumb).getByRole("link", { name: "项目" }),
  ).toHaveAttribute("href", expectedHref);
  expect(screen.getByRole("link", { name: "返回项目" })).toHaveAttribute(
    "href",
    expectedHref,
  );
});

test("移动端 SidebarTrigger 保留在 Header leading 区", async () => {
  setViewportWidth(500);
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
  const breadcrumb = screen.getByRole("navigation", { name: "面包屑导航" });
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

test("长中文 Breadcrumb 保持合法列表结构", async () => {
  renderHeaderAt("/cameras/camera-42");

  const breadcrumb = await screen.findByRole("navigation", {
    name: "面包屑导航",
  });
  const list = breadcrumb.querySelector('[data-slot="breadcrumb-list"]');

  expect(list).not.toBeNull();
  expect(
    Array.from(list?.children ?? []).every(
      (child) => child.tagName.toLowerCase() === "li",
    ),
  ).toBe(true);
  expect(list?.querySelector("li li")).toBeNull();
  expect(within(breadcrumb).getByText(LONG_CAMERA_LABEL)).toHaveAttribute(
    "aria-current",
    "page",
  );
});

test("Breadcrumb 在 Header 中心列内居中", async () => {
  renderHeaderAt("/cameras");

  const breadcrumb = await screen.findByRole("navigation", {
    name: "面包屑导航",
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
    name: "面包屑导航",
  });

  expect(
    within(breadcrumb).getByRole("link", { name: "工作区" }),
  ).toBeInTheDocument();
  expect(
    breadcrumb.querySelector('[data-slot="breadcrumb-ellipsis"]'),
  ).toBeInTheDocument();
  expect(within(breadcrumb).getByText("设置")).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(within(breadcrumb).queryByText("摄像头")).toBeNull();
  expect(within(breadcrumb).queryByText("摄像头 42")).toBeNull();
});
