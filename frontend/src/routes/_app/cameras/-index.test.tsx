import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, test, vi } from "vitest";

import { cameraQueryKeys } from "@/features/cameras/api/camera-query-keys";
import { apiBaseUrl } from "@/lib/api-client";
import { queryClient } from "@/lib/query-client";
import {
  buildCameraPage,
  CAMERA_FIXTURE_SECRET,
} from "@/mocks/cameras/fixtures";
import { createCamerasMswScenario } from "@/mocks/cameras/scenarios";
import { mockServer } from "@/mocks/node";
import { setViewportWidth } from "@/test/browser-mocks";
import { renderAppRoute } from "@/test/render-router";

function renderCameraList(
  scenario: Parameters<typeof createCamerasMswScenario>[0] = "success",
  initialPath = "/cameras",
) {
  mockServer.use(...createCamerasMswScenario(scenario));
  return renderAppRoute(initialPath);
}

test("列表 Card 只展示摘要字段，并用完整默认 search 进入详情", async () => {
  const { container } = renderCameraList();

  expect(
    await screen.findByRole("heading", { level: 2, name: "洗手区 01" }),
  ).toBeInTheDocument();
  expect(screen.getByText("192.0.2.64:554")).toBeVisible();
  expect(screen.getByText("主码流")).toBeVisible();
  expect(screen.getByText("1 / 2 路在线")).toBeVisible();
  expect(screen.getByText("部分离线")).toBeVisible();
  expect(
    screen.getByRole("link", { name: "查看摄像头详情：洗手区 01" }),
  ).toHaveAttribute(
    "href",
    "/cameras/6f9619ff-8b86-4e4f-9f68-bb3f8f6f4f21?page=1&page_size=6",
  );
  expect(
    within(screen.getByRole("region", { name: "摄像头列表" })).getByRole(
      "heading",
      { name: "洗手区 01" },
    ),
  ).toBeVisible();
  const detailLink = screen.getByRole("link", {
    name: "查看摄像头详情：洗手区 01",
  });
  expect(within(detailLink).getByRole("heading", { name: "洗手区 01" })).toBe(
    screen.getByRole("heading", { level: 2, name: "洗手区 01" }),
  );
  expect(detailLink.querySelector("[data-camera-preview]")).toHaveAttribute(
    "data-slot",
    "aspect-ratio",
  );
  expect(detailLink.querySelector("[data-source-status]")).toBeNull();
  expect(detailLink.querySelector("[data-slot='card-footer']")).toBeNull();
  expect(
    screen.getByRole("region", { name: "摄像头列表" }).firstElementChild,
  ).toHaveClass("min-[520px]:grid-cols-2", "min-[1200px]:grid-cols-4");
  expect(container.querySelector("video")).toBeNull();
  expect(document.body.textContent).not.toContain(CAMERA_FIXTURE_SECRET);
  expect(document.body.textContent).not.toContain("rtsp://");
});

test("列表工具栏不显示页面标题和搜索标签，并将搜索与添加操作放在同一行", async () => {
  renderCameraList();

  await screen.findByRole("heading", { level: 2, name: "洗手区 01" });
  const toolbar = screen.getByRole("group", { name: "摄像头列表工具栏" });

  expect(toolbar).toHaveClass("flex", "items-center");
  expect(
    within(toolbar).getByRole("searchbox", { name: "搜索摄像头" }),
  ).toBeVisible();
  expect(
    within(toolbar).getByRole("button", { name: "添加摄像头" }),
  ).toBeVisible();
  expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
  expect(screen.queryByText("管理摄像头连接信息和视频源配置。")).toBeNull();
  expect(screen.queryByText("搜索摄像头")).toBeNull();
});

test("父路由把缺失或非法 search 恢复为统一默认值", async () => {
  const { router } = renderCameraList(
    "success",
    "/cameras?q=%20%20&page=0&page_size=101",
  );

  await screen.findByRole("heading", { level: 2, name: "洗手区 01" });
  expect(router.state.location.search).toEqual({
    q: undefined,
    page: 1,
    page_size: 20,
  });
  expect(screen.getByRole("searchbox", { name: "搜索摄像头" })).toHaveValue("");
});

test.each([
  [390, 4],
  [900, 6],
  [1440, 12],
])(
  "URL 缺少 page_size 时，%dpx 首次进入选择 %d 并在 resize 后保持",
  async (viewportWidth, expectedPageSize) => {
    setViewportWidth(viewportWidth);
    const { router } = renderCameraList();

    await screen.findByRole("heading", { level: 2, name: "洗手区 01" });
    expect(router.state.location.search.page_size).toBe(expectedPageSize);
    expect(router.state.location.href).toContain(
      `page_size=${expectedPageSize}`,
    );

    act(() => setViewportWidth(viewportWidth === 1440 ? 390 : 1440));
    expect(router.state.location.search.page_size).toBe(expectedPageSize);
    expect(router.state.location.href).toContain(
      `page_size=${expectedPageSize}`,
    );
  },
);

test("URL 已提供 page_size 时不使用视口默认值", async () => {
  setViewportWidth(390);
  const { router } = renderCameraList("success", "/cameras?page_size=20");

  await screen.findByRole("heading", { level: 2, name: "洗手区 01" });
  expect(router.state.location.search.page_size).toBe(20);
  expect(router.state.location.href).toContain("page_size=20");
});

test("搜索防抖使用 replace、重置页码，并可立即清除", async () => {
  const user = userEvent.setup();
  const { router } = renderCameraList(
    "search-no-results",
    "/cameras?page=3&page_size=20",
  );
  const navigate = vi.spyOn(router, "navigate");
  const searchbox = await screen.findByRole("searchbox", {
    name: "搜索摄像头",
  });

  await user.type(searchbox, "不存在");
  expect(screen.queryByText("未找到匹配摄像头")).toBeNull();
  expect(await screen.findByText("未找到匹配摄像头")).toBeVisible();
  expect(router.state.location.search).toEqual({
    q: "不存在",
    page: 1,
    page_size: 20,
  });
  expect(navigate).toHaveBeenCalledWith(
    expect.objectContaining({ replace: true }),
  );

  await user.click(screen.getAllByRole("button", { name: "清除搜索" })[0]!);
  await waitFor(() => expect(router.state.location.search.q).toBeUndefined());
  expect(router.state.location.search.page).toBe(1);
});

test("分页 Link 保留查询参数、写入历史，并支持前进后退恢复", async () => {
  const user = userEvent.setup();
  const { router } = renderCameraList(
    "multi-page",
    "/cameras?q=%E5%8C%BA&page=1&page_size=1",
  );

  await screen.findByRole("heading", { level: 2, name: "洗手区 01" });
  const nextLink = screen.getByRole("link", { name: "前往下一页" });
  expect(nextLink).toHaveAttribute(
    "href",
    "/cameras?q=%E5%8C%BA&page=2&page_size=1",
  );

  await user.click(nextLink);
  expect(
    await screen.findByRole("heading", { level: 2, name: "包装区 02" }),
  ).toBeVisible();
  expect(router.state.location.search.page).toBe(2);

  act(() => router.history.back());
  await screen.findByRole("heading", { level: 2, name: "洗手区 01" });
  expect(router.state.location.search.page).toBe(1);

  act(() => router.history.forward());
  await screen.findByRole("heading", { level: 2, name: "包装区 02" });
  expect(router.state.location.search.page).toBe(2);
});

test("Card、详情返回和 Cameras Breadcrumb 都保留列表 search", async () => {
  const user = userEvent.setup();
  const { router } = renderCameraList(
    "multi-page",
    "/cameras?q=%E5%8C%85%E8%A3%85&page=2&page_size=1",
  );
  const expectedListHref = "/cameras?q=%E5%8C%85%E8%A3%85&page=2&page_size=1";

  await screen.findByRole("heading", { level: 2, name: "包装区 02" });
  await user.click(
    screen.getByRole("link", { name: "查看摄像头详情：包装区 02" }),
  );
  await screen.findByRole("heading", { level: 1, name: "洗手区 01" });

  expect(
    within(screen.getByRole("navigation", { name: "面包屑导航" })).getByRole(
      "link",
      { name: "摄像头" },
    ),
  ).toHaveAttribute("href", expectedListHref);
  const backLink = screen.getByRole("link", { name: "返回摄像头列表" });
  expect(backLink).toHaveAttribute("href", expectedListHref);

  await user.click(backLink);
  expect(
    await screen.findByRole("heading", { level: 2, name: "包装区 02" }),
  ).toBeVisible();
  expect(router.state.location.search).toEqual({
    q: "包装",
    page: 2,
    page_size: 1,
  });
});

test.each([
  {
    scenario: "empty-list" as const,
    path: "/cameras",
    state: "empty",
    title: "尚无摄像头",
  },
  {
    scenario: "search-no-results" as const,
    path: "/cameras?q=%E4%B8%8D%E5%AD%98%E5%9C%A8",
    state: "no-results",
    title: "未找到匹配摄像头",
  },
  {
    scenario: "out-of-range" as const,
    path: "/cameras?page=3&page_size=1",
    state: "out-of-range",
    title: "当前页没有摄像头",
  },
])("$state 状态显示独立文案和恢复操作", async (testCase) => {
  renderCameraList(testCase.scenario, testCase.path);

  expect(await screen.findByText(testCase.title)).toBeVisible();
  expect(document.querySelector(`[data-page-state='${testCase.state}']`)).toBe(
    screen.getByText(testCase.title).closest("[data-page-state]"),
  );

  if (testCase.state === "empty") {
    expect(screen.getAllByRole("button", { name: "添加摄像头" })).toHaveLength(
      2,
    );
  } else if (testCase.state === "no-results") {
    expect(
      screen.getAllByRole("button", { name: "清除搜索" }).length,
    ).toBeGreaterThan(0);
  } else {
    expect(screen.getByRole("link", { name: "返回第一页" })).toHaveAttribute(
      "href",
      "/cameras?page=1&page_size=1",
    );
    expect(screen.getByRole("link", { name: "返回上一页" })).toHaveAttribute(
      "href",
      "/cameras?page=2&page_size=1",
    );
  }
});

test("自动重试一次可恢复首次失败，不进入页面错误状态", async () => {
  renderCameraList("initial-failure");

  expect(
    await screen.findByRole(
      "heading",
      { level: 2, name: "洗手区 01" },
      { timeout: 4_000 },
    ),
  ).toBeVisible();
  expect(screen.queryByText("无法加载摄像头列表")).toBeNull();
});

test("首次请求和自动重试均失败后，可重置 Query 并重新执行 loader", async () => {
  const user = userEvent.setup();
  const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
  const { router } = renderCameraList("page-error-recovery");
  const invalidate = vi.spyOn(router, "invalidate");

  expect(
    await screen.findByText("无法加载摄像头列表", {}, { timeout: 4_000 }),
  ).toBeVisible();
  await user.click(screen.getByRole("button", { name: "重试" }));

  expect(invalidate).toHaveBeenCalledTimes(1);
  expect(
    await screen.findByRole("heading", { level: 2, name: "洗手区 01" }),
  ).toBeVisible();
  consoleError.mockRestore();
});

test("后台刷新失败保留 Cards，并显示非阻塞重试操作", async () => {
  renderCameraList("background-refresh-failure");
  await screen.findByRole("heading", { level: 2, name: "洗手区 01" });

  await act(async () => {
    await queryClient.refetchQueries({
      queryKey: cameraQueryKeys.cameras({ page: 1, page_size: 6 }),
    });
  });

  expect(
    await screen.findByText("摄像头列表刷新失败", {}, { timeout: 4_000 }),
  ).toBeVisible();
  expect(
    screen.getByRole("heading", { level: 2, name: "洗手区 01" }),
  ).toBeVisible();
  expect(screen.getByRole("button", { name: "重新刷新" })).toBeVisible();
});

test("后台刷新期间静默保留 Cards，不插入刷新状态行", async () => {
  renderCameraList();
  await screen.findByRole("heading", { level: 2, name: "洗手区 01" });

  let releaseRefresh: (() => void) | undefined;
  const refreshGate = new Promise<void>((resolve) => {
    releaseRefresh = resolve;
  });
  // 首屏完成后覆盖列表 handler，让后台请求保持 pending，确保测试能稳定观察刷新中的 DOM。
  mockServer.use(
    http.get(`${apiBaseUrl.replace(/\/$/, "")}/cameras`, async () => {
      await refreshGate;
      return HttpResponse.json(buildCameraPage());
    }),
  );

  let refreshPromise: Promise<void> | undefined;
  act(() => {
    refreshPromise = queryClient.refetchQueries({
      queryKey: cameraQueryKeys.cameras({ page: 1, page_size: 6 }),
    });
  });
  await waitFor(() =>
    expect(
      queryClient.getQueryState(
        cameraQueryKeys.cameras({ page: 1, page_size: 6 }),
      )?.fetchStatus,
    ).toBe("fetching"),
  );

  expect(screen.queryByText("正在刷新摄像头列表")).toBeNull();
  expect(
    document.querySelector("[data-page-state='background-refreshing']"),
  ).toBeNull();
  expect(
    screen.getByRole("heading", { level: 2, name: "洗手区 01" }),
  ).toBeVisible();

  releaseRefresh?.();
  await act(async () => {
    await refreshPromise;
  });
});
