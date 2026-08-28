import { http, HttpResponse } from "msw";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { cameraQueryKeys } from "@/features/cameras/api/camera-query-keys";
import { apiBaseUrl } from "@/lib/api-client";
import { queryClient } from "@/lib/query-client";
import {
  buildCameraDetail,
  CAMERA_FIXTURE_IDS,
  CAMERA_FIXTURE_SECRET,
  CAMERA_FIXTURE_TIMES,
} from "@/mocks/cameras/fixtures";
import { createCamerasMswScenario } from "@/mocks/cameras/scenarios";
import { mockServer } from "@/mocks/node";
import { setViewportWidth } from "@/test/browser-mocks";
import { renderAppRoute } from "@/test/render-router";

const CAMERA_DETAIL_PATH = `/cameras/${CAMERA_FIXTURE_IDS.primaryCamera}`;

function renderCameraDetail(
  scenario: Parameters<typeof createCamerasMswScenario>[0] = "success",
) {
  mockServer.use(...createCamerasMswScenario(scenario));
  return renderAppRoute(CAMERA_DETAIL_PATH);
}

test("直接 URL 展示连接信息、默认源预览、视频源表格和实体 Breadcrumb", async () => {
  const detail = buildCameraDetail();
  const { container } = renderCameraDetail();

  const heading = await screen.findByRole("heading", {
    level: 1,
    name: detail.name,
  });
  const breadcrumb = screen.getByRole("navigation", { name: "面包屑导航" });

  expect(heading).toBeInTheDocument();
  expect(within(breadcrumb).getByText(detail.name)).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(screen.queryByText(detail.camera_id)).toBeNull();
  expect(screen.getByText(detail.ip_address)).toBeInTheDocument();
  expect(screen.getByText(String(detail.rtsp_port))).toBeInTheDocument();
  expect(screen.getByText(detail.username)).toBeInTheDocument();
  expect(screen.getByText("********")).toBeInTheDocument();
  expect(screen.queryByText(CAMERA_FIXTURE_SECRET)).toBeNull();
  expect(
    container.querySelector(
      `time[datetime="${CAMERA_FIXTURE_TIMES.createdAt}"]`,
    ),
  ).toBeNull();
  expect(
    container.querySelector(
      `time[datetime="${CAMERA_FIXTURE_TIMES.updatedAt}"]`,
    ),
  ).toBeNull();
  expect(
    container.querySelectorAll(
      `time[datetime="${CAMERA_FIXTURE_TIMES.checkedAt}"]`,
    ),
  ).toHaveLength(1);

  const preview = screen.getByRole("region", { name: "默认视频源预览" });
  expect(
    within(preview).getByText(detail.sources[0]?.name ?? ""),
  ).toBeVisible();
  expect(within(preview).queryByText("只读状态预览")).toBeNull();
  expect(within(preview).queryByText(/运行错误|最近检查/)).toBeNull();
  expect(preview.querySelector("[data-camera-status]")).toBeNull();

  const pageHeader = heading.closest("header");
  expect(pageHeader).not.toBeNull();
  expect(pageHeader?.querySelector("[data-camera-status]")).toBeNull();

  const connectionCard = screen
    .getByRole("heading", { name: "连接信息" })
    .closest("[data-slot='card']");
  expect(connectionCard).not.toBeNull();
  expect(connectionCard?.querySelectorAll("[data-camera-status]")).toHaveLength(
    1,
  );
  expect(connectionCard?.querySelector("[data-camera-status]")).toHaveClass(
    "bg-status-degraded",
    "text-status-degraded-foreground",
  );
  expect(
    connectionCard?.querySelector("[data-camera-status] [data-status-dot]"),
  ).toHaveClass("bg-status-degraded-dot");
  expect(screen.getByRole("heading", { name: "摄像头视频源" })).toBeVisible();
  expect(screen.getByRole("columnheader", { name: "预览" })).toBeVisible();
  expect(screen.getByRole("columnheader", { name: "源名称" })).toBeVisible();
  expect(screen.getByRole("columnheader", { name: "RTSP URL" })).toBeVisible();
  expect(screen.getByRole("columnheader", { name: "状态" })).toBeVisible();
  expect(
    screen
      .getAllByRole("row")
      .slice(1)
      .map((row) => within(row).getAllByRole("cell")[1]?.textContent),
  ).toEqual(detail.sources.map((source) => source.name));
  expect(container.querySelectorAll("[data-source-status]")).toHaveLength(
    detail.sources.length,
  );
  const sourceStatusBadges = container.querySelectorAll("[data-source-status]");
  detail.sources.forEach((source, index) => {
    const expectedClassName =
      source.status === "ONLINE"
        ? ["bg-status-online", "text-status-online-foreground"]
        : ["bg-status-offline", "text-status-offline-foreground"];
    expect(sourceStatusBadges[index]).toHaveClass(...expectedClassName);
    expect(
      sourceStatusBadges[index]?.querySelector("[data-status-dot]"),
    ).toHaveClass(
      source.status === "ONLINE"
        ? "bg-status-online-dot"
        : "bg-status-offline-dot",
    );
  });
});

test("密码默认隐藏并允许显隐切换，不显示创建和更新时间", async () => {
  const user = userEvent.setup();
  renderCameraDetail();
  await screen.findByRole("heading", { level: 1, name: "洗手区 01" });

  const showPassword = screen.getByRole("button", { name: "显示密码" });
  expect(screen.getByText("********")).toBeVisible();
  expect(screen.queryByText(CAMERA_FIXTURE_SECRET)).toBeNull();

  await user.click(showPassword);
  expect(screen.getByText(CAMERA_FIXTURE_SECRET)).toBeVisible();
  expect(screen.getByRole("button", { name: "隐藏密码" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  await user.click(screen.getByRole("button", { name: "隐藏密码" }));
  expect(screen.queryByText(CAMERA_FIXTURE_SECRET)).toBeNull();
  expect(screen.getByText("********")).toBeVisible();
});

test("RTSP URL 只以可换行等宽文本展示，占位操作不会发起业务请求", async () => {
  const detail = buildCameraDetail();
  const clipboardWrite = vi.fn();
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: clipboardWrite },
  });
  let playbackRequests = 0;
  mockServer.use(...createCamerasMswScenario("success"));
  // 后注册的专用 handler 优先于场景中的 Playback 成功响应，确保误调用一定会被计数。
  mockServer.use(
    http.post(`${apiBaseUrl}/camera-sources/:sourceId/playback`, () => {
      playbackRequests += 1;
      return HttpResponse.error();
    }),
  );

  const { container } = renderAppRoute(CAMERA_DETAIL_PATH);
  await screen.findByRole("heading", { level: 1, name: detail.name });

  for (const source of detail.sources) {
    const url = screen.getByText(source.rtsp_url);
    expect(url.tagName).toBe("CODE");
    expect(url).toHaveClass("break-all", "font-mono");
    expect(url.closest("a")).toBeNull();
  }

  expect(container.querySelector("video")).toBeNull();
  expect(container.querySelector("table")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "开始预览" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "编辑摄像头" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "删除摄像头" })).toBeDisabled();
  expect(screen.getAllByRole("radio")).toHaveLength(detail.sources.length);
  screen.getAllByRole("radio").forEach((radio) => {
    expect(radio).toHaveAttribute("aria-disabled", "true");
  });
  expect(screen.getAllByRole("radio")[0]).toBeChecked();
  expect(screen.getAllByRole("radio")[1]).not.toBeChecked();
  expect(screen.queryByText(/复制/)).toBeNull();
  expect(clipboardWrite).not.toHaveBeenCalled();
  expect(playbackRequests).toBe(0);
});

test("窄屏保持单列，视频源表格只在组件内横向滚动", async () => {
  setViewportWidth(320);
  const detail = buildCameraDetail({
    sources: [
      {
        name: "用于验证窄屏换行的超长默认视频源名称",
        url_suffix: "Streaming/Channels/101/with/a/very/long/read-only/suffix",
      },
    ],
  });
  mockServer.use(
    http.get(`${apiBaseUrl}/cameras/:cameraId`, () =>
      HttpResponse.json(detail, {
        headers: { "Cache-Control": "no-store" },
      }),
    ),
  );

  const { container } = renderAppRoute(CAMERA_DETAIL_PATH);
  await screen.findByRole("heading", { level: 1, name: detail.name });

  const table = container.querySelector("table");
  expect(table).toBeInTheDocument();
  expect(table).toHaveClass("min-w-3xl");
  expect(table?.parentElement).toHaveClass("overflow-x-auto");
  expect(screen.getByText(detail.sources[0]?.rtsp_url ?? "")).toHaveClass(
    "break-all",
  );
  expect(
    within(screen.getByRole("region", { name: "默认视频源预览" })).getByText(
      "用于验证窄屏换行的超长默认视频源名称",
    ),
  ).toHaveClass("wrap-break-word");
});

test("深色主题与 Reduced Motion 使用现有主题和无动画状态类", async () => {
  const user = userEvent.setup();
  const { container } = renderCameraDetail();
  await screen.findByRole("heading", { level: 1, name: "洗手区 01" });

  await user.click(screen.getByRole("button", { name: "切换为深色主题" }));
  expect(document.documentElement).toHaveClass("dark");
  expect(container.querySelector("[data-slot='card']")).toHaveClass("bg-card");
  expect(
    container.querySelectorAll(".motion-reduce\\:transition-none").length,
  ).toBeGreaterThan(0);
});

test("站内进入详情后聚焦实体标题，返回列表仍是语义链接", async () => {
  mockServer.use(...createCamerasMswScenario("success"));
  const { router } = renderAppRoute("/cameras");
  await screen.findByRole("heading", { level: 1, name: "摄像头" });

  await act(async () => {
    await router.navigate({
      to: "/cameras/$cameraId",
      params: { cameraId: CAMERA_FIXTURE_IDS.primaryCamera },
    });
  });
  const heading = await screen.findByRole("heading", {
    level: 1,
    name: "洗手区 01",
  });

  await waitFor(() => expect(heading).toHaveFocus());
  expect(
    screen
      .getAllByRole("link", { name: "返回摄像头列表" })
      .some((link) => link.getAttribute("href") === "/cameras"),
  ).toBe(true);
});

test("浏览器刷新等价于重新从直接 URL 加载同一详情", async () => {
  const first = renderCameraDetail();
  expect(
    await screen.findByRole("heading", { level: 1, name: "洗手区 01" }),
  ).toBeInTheDocument();

  first.unmount();
  queryClient.clear();
  mockServer.resetHandlers();

  renderCameraDetail();
  expect(
    await screen.findByRole("heading", { level: 1, name: "洗手区 01" }),
  ).toBeInTheDocument();
  expect(
    within(screen.getByRole("navigation", { name: "面包屑导航" })).getByText(
      "洗手区 01",
    ),
  ).toBeInTheDocument();
});

test("可信 CAMERA_NOT_FOUND 进入 Camera Not Found", async () => {
  renderCameraDetail("camera-not-found");

  expect(
    await screen.findByRole("heading", { level: 1, name: "未找到摄像头" }),
  ).toBeInTheDocument();
  expect(
    screen
      .getAllByRole("link", { name: "返回摄像头列表" })
      .some((link) => link.getAttribute("href") === "/cameras"),
  ).toBe(true);
});

test("数据库错误进入 Cameras Route Error，后台刷新失败仍保留旧详情", async () => {
  const consoleError = vi
    .spyOn(console, "error")
    .mockImplementation(() => undefined);
  const initial = renderCameraDetail("dependency-unavailable");

  expect(
    await screen.findByRole(
      "heading",
      {
        level: 1,
        name: "无法加载摄像头内容",
      },
      { timeout: 4_000 },
    ),
  ).toBeInTheDocument();
  initial.unmount();
  queryClient.clear();
  mockServer.resetHandlers();

  renderCameraDetail("background-refresh-failure");
  expect(
    await screen.findByRole("heading", { level: 1, name: "洗手区 01" }),
  ).toBeInTheDocument();

  await act(async () => {
    await queryClient.refetchQueries({
      queryKey: cameraQueryKeys.camera(CAMERA_FIXTURE_IDS.primaryCamera),
    });
  });
  expect(
    screen.getByRole("heading", { level: 1, name: "洗手区 01" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("heading", { name: "无法加载摄像头内容" }),
  ).toBeNull();

  consoleError.mockRestore();
});
