import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { cameraQueryKeys } from "@/features/cameras/api/camera-query-keys";
import { queryClient } from "@/lib/query-client";
import {
  buildCameraDetail,
  CAMERA_FIXTURE_IDS,
} from "@/mocks/cameras/fixtures";
import { createCamerasMswScenario } from "@/mocks/cameras/scenarios";
import { mockServer } from "@/mocks/node";
import { renderAppRoute } from "@/test/render-router";

const CAMERA_DETAIL_PATH = `/cameras/${CAMERA_FIXTURE_IDS.primaryCamera}`;

function renderCameraDetail(
  scenario: Parameters<typeof createCamerasMswScenario>[0] = "success",
) {
  mockServer.use(...createCamerasMswScenario(scenario));
  return renderAppRoute(CAMERA_DETAIL_PATH);
}

test("直接 URL 加载详情区域、默认预览和实体 Breadcrumb", async () => {
  const detail = buildCameraDetail();
  renderCameraDetail();

  const heading = await screen.findByRole(
    "heading",
    {
      level: 1,
      name: detail.name,
    },
    { timeout: 3_000 },
  );
  const breadcrumb = screen.getByRole("navigation", { name: "面包屑导航" });

  expect(heading).toBeInTheDocument();
  expect(within(breadcrumb).getByText(detail.name)).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(screen.queryByText(detail.camera_id)).toBeNull();
  expect(screen.getByRole("region", { name: "视频源预览" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "连接信息" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "摄像头视频源" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "删除摄像头" })).toBeVisible();
  expect(screen.getByRole("button", { name: "停止预览" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "编辑摄像头" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "删除摄像头" })).toBeDisabled();
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
  await screen.findByRole("searchbox", { name: "搜索摄像头" });

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
      .some(
        (link) => link.getAttribute("href") === "/cameras?page=1&page_size=6",
      ),
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
      .some(
        (link) => link.getAttribute("href") === "/cameras?page=1&page_size=6",
      ),
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
