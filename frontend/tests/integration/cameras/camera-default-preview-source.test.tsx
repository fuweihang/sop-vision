import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse, type RequestHandler } from "msw";
import { expect, test, vi } from "vitest";

import { cameraQueryKeys } from "@/features/cameras/api/camera-query-keys";
import { apiBaseUrl } from "@/lib/api-client";
import { queryClient } from "@/lib/query-client";
import {
  buildCameraDetail,
  buildDefaultPreviewSourceResponse,
  CAMERA_FIXTURE_IDS,
} from "@/mocks/cameras/fixtures";
import { createCamerasMswScenario } from "@/mocks/cameras/scenarios";
import { mockServer } from "@/mocks/node";
import { renderAppRoute } from "@/test/render-router";

const cameraPath = `/cameras/${CAMERA_FIXTURE_IDS.primaryCamera}`;
const camerasUrl = `${apiBaseUrl.replace(/\/$/, "")}/cameras`;
const cameraUrl = `${camerasUrl}/${CAMERA_FIXTURE_IDS.primaryCamera}`;
const defaultSourceUrl = `${cameraUrl}/default-preview-source`;

async function openCameraDetail(
  scenario: Parameters<typeof createCamerasMswScenario>[0] = "success",
  handlers: RequestHandler[] = [],
) {
  mockServer.use(...createCamerasMswScenario(scenario));
  // 测试专用 handler 后注册，覆盖场景中的同 operation handler，但保留其余五个 API 边界。
  mockServer.use(...handlers);
  const rendered = renderAppRoute(cameraPath);
  const sources = await screen.findByRole("radiogroup", {
    name: "默认预览源",
  });
  return { user: userEvent.setup(), sources, ...rendered };
}

function secondaryRadio(container: HTMLElement, sourceName = "子码流") {
  return within(container).getByRole("radio", {
    name: `设“${sourceName}”为默认预览源`,
  });
}

test("成功 PATCH 不乐观更新，并用重新读取的详情和列表确认默认 ID", async () => {
  const invalidate = vi.spyOn(queryClient, "invalidateQueries");
  const { user, sources } = await openCameraDetail();
  const radio = secondaryRadio(sources);

  expect(radio).toBeEnabled();
  expect(radio).not.toBeChecked();
  await user.click(radio);

  expect(await screen.findByText("默认预览源已更新")).toBeInTheDocument();
  await waitFor(() => expect(radio).toBeChecked());
  expect(invalidate).toHaveBeenCalledWith({
    queryKey: ["cameras"],
    refetchType: "all",
  });
  expect(invalidate).toHaveBeenCalledWith({
    queryKey: cameraQueryKeys.camera(CAMERA_FIXTURE_IDS.primaryCamera),
    refetchType: "all",
  });
  await waitFor(() =>
    expect(queryClient.getMutationCache().getAll()).toHaveLength(0),
  );
});

test("修改默认预览源只更新 Card 配置，Detail 继续播放排序第一路", async () => {
  const { user, sources } = await openCameraDetail("whep-player");
  const radio = secondaryRadio(sources, "彩条测试图");

  expect(
    screen.getByRole("combobox", { name: "切换预览源" }),
  ).toHaveTextContent("动态测试图");

  await user.click(radio);

  await waitFor(() => expect(radio).toBeChecked());
  expect(
    screen.getByRole("combobox", { name: "切换预览源" }),
  ).toHaveTextContent("动态测试图");
});

test("PATCH 未完成时保持旧默认 ID、禁用全部单选并阻止快速重复提交", async () => {
  const camera = buildCameraDetail();
  let requestCount = 0;
  let finishRequest = () => {};
  const pendingRequest = new Promise<void>((resolve) => {
    finishRequest = resolve;
  });
  const { user, sources } = await openCameraDetail("success", [
    http.patch(defaultSourceUrl, async () => {
      requestCount += 1;
      await pendingRequest;
      return HttpResponse.json(
        buildDefaultPreviewSourceResponse(
          camera,
          CAMERA_FIXTURE_IDS.secondarySource,
        ),
      );
    }),
  ]);
  const radios = within(sources).getAllByRole("radio");
  const radio = secondaryRadio(sources);

  await user.click(radio);
  expect(
    await screen.findByRole("status", {
      name: "正在设置默认预览源",
    }),
  ).toBeVisible();
  radios.forEach((item) =>
    expect(item).toHaveAttribute("aria-disabled", "true"),
  );
  expect(radios[0]).toBeChecked();
  expect(radio).not.toBeChecked();
  await user.click(radio);
  expect(requestCount).toBe(1);

  act(() => finishRequest());
  await waitFor(() =>
    radios.forEach((item) =>
      expect(item).not.toHaveAttribute("aria-disabled", "true"),
    ),
  );
  expect(requestCount).toBe(1);
});

test("确定失败显示固定提示、恢复操作并保留旧默认 ID", async () => {
  const { user, sources } = await openCameraDetail("nested-validation-error");
  const radio = secondaryRadio(sources);

  await user.click(radio);

  expect(await screen.findByText("未能设置默认预览源")).toBeVisible();
  expect(
    screen.getByText("该视频源已不存在或不属于当前摄像头，请刷新后重试。"),
  ).toBeVisible();
  expect(radio).toBeEnabled();
  expect(radio).not.toBeChecked();
});

test("结果未知在详情重新读取成功前持续显示，成功后自动解除", async () => {
  const camera = buildCameraDetail();
  let detailRequestCount = 0;
  let finishConfirmation = () => {};
  const pendingConfirmation = new Promise<void>((resolve) => {
    finishConfirmation = resolve;
  });
  const { user, sources } = await openCameraDetail("success", [
    http.get(cameraUrl, async () => {
      detailRequestCount += 1;
      if (detailRequestCount > 1) {
        await pendingConfirmation;
      }
      return HttpResponse.json(camera, {
        headers: { "Cache-Control": "no-store" },
      });
    }),
    http.patch(defaultSourceUrl, () => HttpResponse.error()),
  ]);
  const radio = secondaryRadio(sources);

  await user.click(radio);

  expect(await screen.findByText("默认源设置结果未知")).toBeVisible();
  expect(radio).toBeEnabled();
  expect(radio).not.toBeChecked();

  act(() => finishConfirmation());
  await waitFor(() =>
    expect(screen.queryByText("默认源设置结果未知")).toBeNull(),
  );
  expect(detailRequestCount).toBeGreaterThan(1);
});

test("结果未知的详情重读失败时保留提示，用户可显式再次发送 PATCH", async () => {
  const camera = buildCameraDetail();
  let detailRequestCount = 0;
  let patchRequestCount = 0;
  const { user, sources } = await openCameraDetail("success", [
    http.get(cameraUrl, () => {
      detailRequestCount += 1;
      return detailRequestCount === 1
        ? HttpResponse.json(camera, {
            headers: { "Cache-Control": "no-store" },
          })
        : HttpResponse.error();
    }),
    http.patch(defaultSourceUrl, () => {
      patchRequestCount += 1;
      return HttpResponse.error();
    }),
  ]);
  const radio = secondaryRadio(sources);

  await user.click(radio);
  expect(await screen.findByText("默认源设置结果未知")).toBeVisible();
  await waitFor(() => expect(detailRequestCount).toBeGreaterThanOrEqual(3));
  expect(radio).toBeEnabled();

  await user.click(radio);
  await waitFor(() => expect(patchRequestCount).toBe(2));
  expect(screen.queryByRole("alertdialog", { name: /再次/ })).toBeNull();
  expect(screen.getByText("默认源设置结果未知")).toBeVisible();
});
