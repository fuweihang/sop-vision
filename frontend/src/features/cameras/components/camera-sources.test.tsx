import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { expect, test } from "vitest";

import type { CameraDetail } from "@/features/cameras/api/cameras-api";
import { CameraSources } from "@/features/cameras/components/camera-sources";
import { apiClient } from "@/lib/api-client";
import { buildCameraDetail } from "@/mocks/cameras/fixtures";

function renderCameraSources(camera: CameraDetail) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <CameraSources camera={camera} apiClient={apiClient} />
    </QueryClientProvider>,
  );
}

test("按响应顺序展示完整 Source 表格和只读默认源", () => {
  const camera = buildCameraDetail();
  const { container } = renderCameraSources(camera);

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
  ).toEqual(camera.sources.map((source) => source.name));

  const radios = screen.getAllByRole("radio");
  expect(radios).toHaveLength(camera.sources.length);
  radios.forEach((radio) => expect(radio).toBeEnabled());
  expect(radios[0]).toBeChecked();
  expect(radios[1]).not.toBeChecked();

  const sourceStatusBadges = container.querySelectorAll("[data-source-status]");
  expect(sourceStatusBadges).toHaveLength(camera.sources.length);
  camera.sources.forEach((source, index) => {
    expect(sourceStatusBadges[index]).toHaveClass(
      source.status === "ONLINE" ? "bg-status-online" : "bg-status-offline",
    );
  });
});

test("RTSP URL 保持可换行等宽文本，窄容器只让表格区域横向滚动", () => {
  const camera = buildCameraDetail({
    sources: [
      {
        name: "用于验证窄屏换行的超长默认视频源名称",
        url_suffix: "Streaming/Channels/101/with/a/very/long/read-only/suffix",
      },
    ],
  });
  const { container } = renderCameraSources(camera);

  const table = container.querySelector("table");
  expect(table).toHaveClass("min-w-3xl");
  expect(table?.parentElement).toHaveClass("overflow-x-auto");
  for (const source of camera.sources) {
    const url = screen.getByText(source.rtsp_url);
    expect(url.tagName).toBe("CODE");
    expect(url).toHaveClass("break-all", "font-mono");
    expect(url.closest("a")).toBeNull();
  }
});
