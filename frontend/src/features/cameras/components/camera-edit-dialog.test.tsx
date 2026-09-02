import {
  act,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, test, vi } from "vitest";

import { cameraQueryKeys } from "@/features/cameras/api/camera-query-keys";
import type { CameraUpdateRequest } from "@/features/cameras/api/cameras-api";
import { apiBaseUrl } from "@/lib/api-client";
import { queryClient } from "@/lib/query-client";
import {
  buildCameraDetail,
  buildProblem,
  CAMERA_FIXTURE_IDS,
  CAMERA_FIXTURE_SECRET,
} from "@/mocks/cameras/fixtures";
import { createCamerasMswScenario } from "@/mocks/cameras/scenarios";
import { mockServer } from "@/mocks/node";
import { renderAppRoute } from "@/test/render-router";

const cameraDetailPath = `/cameras/${CAMERA_FIXTURE_IDS.primaryCamera}`;
const camerasUrl = `${apiBaseUrl.replace(/\/$/, "")}/cameras`;
const cameraUrl = `${camerasUrl}/${CAMERA_FIXTURE_IDS.primaryCamera}`;

function problemResponse(
  status: number,
  code: string,
  errors: ReturnType<typeof buildProblem>["errors"] = [],
) {
  const traceId = "tr_camera_edit_test";
  return HttpResponse.json(
    buildProblem({
      status,
      code,
      instance: `/api/v1/cameras/${CAMERA_FIXTURE_IDS.primaryCamera}`,
      traceId,
      errors,
    }),
    {
      status,
      headers: {
        "Content-Type": "application/problem+json",
        "X-Trace-Id": traceId,
      },
    },
  );
}

async function openEditDialog() {
  const user = userEvent.setup();
  const rendered = renderAppRoute(cameraDetailPath);
  await user.click(
    await screen.findByRole(
      "button",
      { name: "编辑摄像头" },
      { timeout: 3_000 },
    ),
  );
  const dialog = await screen.findByRole("dialog", { name: "编辑摄像头" });
  return { user, dialog, ...rendered };
}

test("打开时初始化完整草稿，详情轮询更新页面但不覆盖正在编辑的值", async () => {
  mockServer.use(...createCamerasMswScenario("success"));
  const initialCamera = buildCameraDetail();
  const { user, dialog } = await openEditDialog();

  expect(within(dialog).getByLabelText("摄像头名称")).toHaveValue(
    initialCamera.name,
  );
  expect(within(dialog).getByLabelText("密码")).toHaveValue(
    initialCamera.password,
  );
  expect(
    within(dialog).getAllByTestId("camera-edit-source-editor"),
  ).toHaveLength(initialCamera.sources.length);

  const nameInput = within(dialog).getByLabelText("摄像头名称");
  await user.clear(nameInput);
  await user.type(nameInput, "用户尚未保存的名称");

  act(() => {
    queryClient.setQueryData(cameraQueryKeys.camera(initialCamera.camera_id), {
      ...initialCamera,
      name: "轮询返回的新名称",
    });
  });

  await waitFor(() =>
    expect(document.querySelector("[data-route-focus]")).toHaveTextContent(
      "轮询返回的新名称",
    ),
  );
  expect(nameInput).toHaveValue("用户尚未保存的名称");
});

test("删除默认源、添加和重排后只提交 API ID 与最终数组顺序", async () => {
  const camera = buildCameraDetail();
  let requestBody: CameraUpdateRequest | undefined;
  mockServer.use(...createCamerasMswScenario("success"));
  mockServer.use(
    http.put(cameraUrl, async ({ request }) => {
      requestBody = (await request.json()) as CameraUpdateRequest;
      return HttpResponse.json(camera, {
        headers: { "Cache-Control": "no-store" },
      });
    }),
  );
  const { user, dialog } = await openEditDialog();

  expect(
    within(dialog).getByRole("button", { name: "删除视频源 1" }),
  ).toBeEnabled();
  await user.click(
    within(dialog).getByRole("button", { name: "删除视频源 1" }),
  );
  expect(
    within(dialog).getByRole("radio", { name: /视频源 1.*当前默认/ }),
  ).toBeChecked();
  expect(
    within(dialog).getByRole("button", { name: "删除视频源 1" }),
  ).toBeDisabled();

  await user.click(within(dialog).getByRole("button", { name: "添加视频源" }));
  const names = within(dialog).getAllByLabelText("名称");
  const suffixes = within(dialog).getAllByLabelText("URL 后缀");
  await user.type(names[1]!, "新增码流");
  await user.type(suffixes[1]!, "Streaming/Channels/201");
  await user.click(
    within(dialog).getByRole("button", { name: "上移视频源 2" }),
  );
  await user.click(within(dialog).getByRole("radio", { name: /视频源 1/ }));
  await user.click(within(dialog).getByRole("button", { name: "保存修改" }));

  await waitFor(() =>
    expect(screen.queryByRole("dialog", { name: "编辑摄像头" })).toBeNull(),
  );
  expect(requestBody?.sources).toEqual([
    {
      name: "新增码流",
      url_suffix: "Streaming/Channels/201",
      is_default_preview: true,
    },
    {
      source_id: camera.sources[1]!.source_id,
      name: camera.sources[1]!.name,
      url_suffix: camera.sources[1]!.url_suffix,
      is_default_preview: false,
    },
  ]);
  expect(JSON.stringify(requestBody)).not.toContain('"id"');
  expect(await screen.findByText("摄像头已更新")).toBeInTheDocument();
  await waitFor(() =>
    expect(queryClient.getMutationCache().getAll()).toHaveLength(0),
  );
});

test("脏表单关闭和路由离开都先确认，留下时保留草稿，丢弃后恢复触发按钮焦点", async () => {
  mockServer.use(...createCamerasMswScenario("success"));
  const { user, dialog, router } = await openEditDialog();
  const nameInput = within(dialog).getByLabelText("摄像头名称");
  await user.type(nameInput, " 已修改");

  await user.click(within(dialog).getByRole("button", { name: "取消" }));
  const discardDialog = await screen.findByRole("alertdialog", {
    name: "丢弃未保存修改？",
  });
  await user.click(
    within(discardDialog).getByRole("button", { name: "留下继续编辑" }),
  );
  expect(screen.getByRole("dialog", { name: "编辑摄像头" })).toBeVisible();
  expect((nameInput as HTMLInputElement).value).toMatch(/已修改$/);

  void router.navigate({ to: "/tasks" });
  const routeDialog = await screen.findByRole("alertdialog", {
    name: "丢弃未保存修改？",
  });
  await user.click(
    within(routeDialog).getByRole("button", { name: "留下继续编辑" }),
  );
  expect(router.state.location.pathname).toBe(cameraDetailPath);
  expect((nameInput as HTMLInputElement).value).toMatch(/已修改$/);

  await user.keyboard("{Escape}");
  await user.click(
    within(
      await screen.findByRole("alertdialog", {
        name: "丢弃未保存修改？",
      }),
    ).getByRole("button", { name: "留下继续编辑" }),
  );
  expect(screen.getByRole("dialog", { name: "编辑摄像头" })).toBeVisible();

  const overlay = document.querySelector('[data-slot="dialog-overlay"]');
  if (overlay === null) {
    throw new Error("编辑 Dialog 缺少背景层。");
  }
  fireEvent.pointerDown(overlay);
  fireEvent.click(overlay);
  await user.click(
    within(
      await screen.findByRole("alertdialog", {
        name: "丢弃未保存修改？",
      }),
    ).getByRole("button", { name: "确认丢弃" }),
  );
  await waitFor(() =>
    expect(screen.queryByRole("dialog", { name: "编辑摄像头" })).toBeNull(),
  );
  expect(screen.getByRole("button", { name: "编辑摄像头" })).toHaveFocus();
});

test("结果未知重新读取成功仍保留草稿，再次保存确认前和取消后都不发送新 PUT", async () => {
  const initialCamera = buildCameraDetail();
  let detailRequestCount = 0;
  let updateRequestCount = 0;
  mockServer.use(
    http.get(cameraUrl, () => {
      detailRequestCount += 1;
      return HttpResponse.json(
        detailRequestCount === 1
          ? initialCamera
          : { ...initialCamera, name: "重新读取的服务端名称" },
        { headers: { "Cache-Control": "no-store" } },
      );
    }),
    http.put(cameraUrl, () => {
      updateRequestCount += 1;
      return HttpResponse.error();
    }),
  );
  const invalidate = vi.spyOn(queryClient, "invalidateQueries");
  const { user, dialog } = await openEditDialog();
  const input = within(dialog).getByLabelText("摄像头名称");
  await user.clear(input);
  await user.type(input, "需要保留的本地草稿");
  await user.click(within(dialog).getByRole("button", { name: "保存修改" }));

  expect(await within(dialog).findByText("更新结果未知")).toBeInTheDocument();
  await waitFor(() => expect(detailRequestCount).toBeGreaterThan(1));
  expect(input).toHaveValue("需要保留的本地草稿");
  expect(updateRequestCount).toBe(1);
  expect(invalidate).toHaveBeenCalledWith({
    queryKey: ["cameras"],
    refetchType: "all",
  });
  expect(invalidate).toHaveBeenCalledWith({
    queryKey: cameraQueryKeys.camera(initialCamera.camera_id),
    refetchType: "all",
  });

  await user.click(within(dialog).getByRole("button", { name: "保存修改" }));
  const retryDialog = await screen.findByRole("alertdialog", {
    name: "再次发送完整更新？",
  });
  expect(updateRequestCount).toBe(1);
  await user.click(
    within(retryDialog).getByRole("button", { name: "暂不发送" }),
  );
  expect(updateRequestCount).toBe(1);
  expect(input).toHaveValue("需要保留的本地草稿");

  await user.click(within(dialog).getByRole("button", { name: "保存修改" }));
  await user.click(
    within(
      await screen.findByRole("alertdialog", {
        name: "再次发送完整更新？",
      }),
    ).getByRole("button", { name: "确认再次保存" }),
  );
  await waitFor(() => expect(updateRequestCount).toBe(2));
  expect(await within(dialog).findByText("更新结果未知")).toBeInTheDocument();
  expect(within(dialog).queryByText(CAMERA_FIXTURE_SECRET)).toBeNull();
  await waitFor(() =>
    expect(queryClient.getMutationCache().getAll()).toHaveLength(0),
  );
});

test("结果未知后的重新读取失败继续显示未知状态且不覆盖草稿", async () => {
  const initialCamera = buildCameraDetail();
  let detailRequestCount = 0;
  mockServer.use(
    http.get(cameraUrl, () => {
      detailRequestCount += 1;
      return detailRequestCount === 1
        ? HttpResponse.json(initialCamera, {
            headers: { "Cache-Control": "no-store" },
          })
        : HttpResponse.error();
    }),
    http.put(cameraUrl, () => HttpResponse.error()),
  );
  const { user, dialog } = await openEditDialog();
  const input = within(dialog).getByLabelText("摄像头名称");
  await user.clear(input);
  await user.type(input, "读取失败也要保留的草稿");
  await user.click(within(dialog).getByRole("button", { name: "保存修改" }));

  expect(await within(dialog).findByText("更新结果未知")).toBeInTheDocument();
  await waitFor(() => expect(detailRequestCount).toBeGreaterThanOrEqual(3));
  expect(input).toHaveValue("读取失败也要保留的草稿");
  expect(screen.getByRole("dialog", { name: "编辑摄像头" })).toBeVisible();
});

test("提交期间锁定字段、关闭和路由离开，完成前只发送一条请求", async () => {
  const camera = buildCameraDetail();
  let finishRequest = () => {};
  const pendingRequest = new Promise<void>((resolve) => {
    finishRequest = resolve;
  });
  let requestCount = 0;
  mockServer.use(...createCamerasMswScenario("success"));
  mockServer.use(
    http.put(cameraUrl, async () => {
      requestCount += 1;
      await pendingRequest;
      return HttpResponse.json(camera, {
        headers: { "Cache-Control": "no-store" },
      });
    }),
  );
  const { user, dialog, router } = await openEditDialog();
  await user.type(within(dialog).getByLabelText("摄像头名称"), " 已修改");
  await user.click(within(dialog).getByRole("button", { name: "保存修改" }));

  expect(
    await within(dialog).findByRole("button", { name: /正在保存/ }),
  ).toBeDisabled();
  expect(within(dialog).getByLabelText("摄像头名称")).toBeDisabled();
  expect(within(dialog).getByRole("button", { name: "取消" })).toBeDisabled();
  expect(within(dialog).queryByRole("button", { name: "关闭" })).toBeNull();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.getByRole("dialog", { name: "编辑摄像头" })).toBeVisible();

  void router.navigate({ to: "/tasks" });
  await act(() => Promise.resolve());
  expect(router.state.location.pathname).toBe(cameraDetailPath);
  expect(
    screen.queryByRole("alertdialog", { name: "丢弃未保存修改？" }),
  ).toBeNull();
  expect(requestCount).toBe(1);

  act(() => finishRequest());
  await waitFor(() =>
    expect(screen.queryByRole("dialog", { name: "编辑摄像头" })).toBeNull(),
  );
  expect(requestCount).toBe(1);
});

test("隐藏 source_id 的 422 显示在对应 Source 行且保留全部输入", async () => {
  mockServer.use(...createCamerasMswScenario("success"));
  mockServer.use(
    http.put(cameraUrl, () =>
      problemResponse(422, "VALIDATION_ERROR", [
        {
          field: "sources[1].source_id",
          code: "SOURCE_NOT_OWNED_BY_CAMERA",
          detail: "该视频源不属于当前摄像头。",
        },
      ]),
    ),
  );
  const { user, dialog } = await openEditDialog();
  const nameInput = within(dialog).getByLabelText("摄像头名称");
  await user.type(nameInput, " 保留输入");
  await user.click(within(dialog).getByRole("button", { name: "保存修改" }));

  const rows = within(dialog).getAllByTestId("camera-edit-source-editor");
  expect(
    await within(rows[1]!).findByText("该视频源不属于当前摄像头。"),
  ).toBeInTheDocument();
  expect((nameInput as HTMLInputElement).value).toMatch(/保留输入$/);
});
