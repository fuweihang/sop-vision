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

// 通过真实 `/cameras` Route 验证 Dialog 组合，避免拆分后只验证孤立子组件。

import type { CameraCreateRequest } from "@/features/cameras/api/cameras-api";
import { apiBaseUrl } from "@/lib/api-client";
import { queryClient } from "@/lib/query-client";
import {
  buildCameraPage,
  CAMERA_FIXTURE_IDS,
  CAMERA_FIXTURE_SECRET,
} from "@/mocks/cameras/fixtures";
import { createCamerasMswScenario } from "@/mocks/cameras/scenarios";
import { mockServer } from "@/mocks/node";
import { renderAppRoute } from "../../support/render-router";

const camerasUrl = `${apiBaseUrl.replace(/\/$/, "")}/cameras`;

function useScenario(name: Parameters<typeof createCamerasMswScenario>[0]) {
  mockServer.use(...createCamerasMswScenario(name));
}

function registerSuccessfulList() {
  // Dialog 用例只关心写请求；真实列表路由仍需要一个明确、非敏感的 loader 响应。
  mockServer.use(
    http.get(camerasUrl, () => HttpResponse.json(buildCameraPage())),
  );
}

async function openDialog() {
  const user = userEvent.setup();
  registerSuccessfulList();
  renderAppRoute("/cameras");
  await user.click(
    await screen.findByRole(
      "button",
      { name: "添加摄像头" },
      { timeout: 3_000 },
    ),
  );
  const dialog = await screen.findByRole("dialog", { name: "添加摄像头" });
  return { user, dialog };
}

async function fillValidCamera(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("摄像头名称"), "洗手区 01");
  await user.type(screen.getByLabelText("IP 地址"), "192.0.2.64");
  await user.type(screen.getByLabelText("用户名"), "camera-user");
  await user.type(screen.getByLabelText("密码"), "camera-password");
  await user.type(screen.getAllByLabelText("名称")[0]!, "主码流");
  await user.type(
    screen.getAllByLabelText("URL 后缀")[0]!,
    "Streaming/Channels/101",
  );
}

test("页面保留已加载列表，并由唯一主操作打开 shadcn Dialog", async () => {
  const { dialog } = await openDialog();

  // Modal 打开后页面会被 Base UI 正确标记为 inert，因此这里只确认列表内容仍存在于 DOM。
  expect(screen.getByText("洗手区 01")).toBeInTheDocument();
  expect(within(dialog).getByLabelText("RTSP 端口")).toHaveValue(554);
  expect(within(dialog).getByLabelText("IP 地址")).not.toHaveAttribute(
    "placeholder",
  );
  expect(within(dialog).getByLabelText("用户名")).not.toHaveAttribute(
    "placeholder",
  );
  expect(within(dialog).getAllByLabelText("名称")[0]).toHaveAttribute(
    "placeholder",
    "例如：通道 1 主码流",
  );
  expect(within(dialog).getAllByLabelText("URL 后缀")[0]).toHaveAttribute(
    "placeholder",
    "例如：Stream/Channels/101",
  );
  expect(within(dialog).getAllByTestId("camera-source-editor")).toHaveLength(1);
  expect(within(dialog).getByRole("radio", { name: /视频源 1/ })).toBeChecked();
  expect(
    within(dialog).getByRole("button", { name: "删除视频源 1" }),
  ).toBeDisabled();
  expect(
    within(dialog).getByRole("button", { name: "上移视频源 1" }),
  ).toBeDisabled();
  expect(
    within(dialog).getByRole("button", { name: "下移视频源 1" }),
  ).toBeDisabled();
  expect(
    within(dialog).getByText("保存设备连接信息和至少一路视频源。"),
  ).toBeInTheDocument();
  expect(within(dialog).queryByText("连接信息", { exact: true })).toBeNull();
  expect(
    within(dialog).queryByText(/摄像头名称和 IP 地址不要求唯一/),
  ).toBeNull();
  expect(within(dialog).queryByText(/密码不会出现在/)).toBeNull();
  expect(within(dialog).queryByText(/预览地址/)).toBeNull();
});

test("Dialog 打开聚焦首个字段，取消后把焦点还给触发按钮", async () => {
  const user = userEvent.setup();
  registerSuccessfulList();
  renderAppRoute("/cameras");
  const trigger = await screen.findByRole("button", { name: "添加摄像头" });

  await user.click(trigger);
  expect(await screen.findByLabelText("摄像头名称")).toHaveFocus();
  await user.click(screen.getByRole("button", { name: "取消" }));

  await waitFor(() =>
    expect(screen.queryByRole("dialog", { name: "添加摄像头" })).toBeNull(),
  );
  expect(trigger).toHaveFocus();
});

test("新增、切换默认、排序和删除 Source 保持当前视觉顺序与默认身份", async () => {
  const { user, dialog } = await openDialog();
  const firstName = within(dialog).getAllByLabelText("名称")[0]!;
  const firstSuffix = within(dialog).getAllByLabelText("URL 后缀")[0]!;
  await user.type(firstName, "主码流");
  await user.type(firstSuffix, "Streaming/Channels/101");

  await user.click(within(dialog).getByRole("button", { name: "添加视频源" }));
  const names = within(dialog).getAllByLabelText("名称");
  const suffixes = within(dialog).getAllByLabelText("URL 后缀");
  await user.type(names[1]!, "子码流");
  await user.type(suffixes[1]!, "Streaming/Channels/102");
  await user.click(within(dialog).getByRole("radio", { name: /视频源 2/ }));
  expect(within(dialog).getAllByLabelText("名称")[0]).toHaveValue("主码流");
  expect(within(dialog).getAllByLabelText("名称")[1]).toHaveValue("子码流");
  expect(
    within(dialog).getByRole("radio", { name: /视频源 2.*当前默认/ }),
  ).toBeChecked();

  await user.click(
    within(dialog).getByRole("button", { name: "上移视频源 2" }),
  );
  expect(within(dialog).getAllByLabelText("名称")[0]).toHaveValue("子码流");
  expect(within(dialog).getAllByLabelText("名称")[1]).toHaveValue("主码流");
  expect(
    within(dialog).getByRole("radio", { name: /视频源 1.*当前默认/ }),
  ).toBeChecked();
  expect(
    within(dialog).getByRole("button", { name: "上移视频源 1" }),
  ).toBeDisabled();
  expect(
    within(dialog).getByRole("button", { name: "下移视频源 2" }),
  ).toBeDisabled();

  await user.click(
    within(dialog).getByRole("button", { name: "删除视频源 1" }),
  );
  expect(within(dialog).getAllByTestId("camera-source-editor")).toHaveLength(1);
  expect(within(dialog).getAllByLabelText("名称")[0]).toHaveValue("主码流");
  expect(
    within(dialog).getByRole("radio", { name: /视频源 1.*当前默认/ }),
  ).toBeChecked();
});

test("十路 Source 保持在有界滚动 Body 中且排序按钮边界正确", async () => {
  const { user, dialog } = await openDialog();
  const addButton = within(dialog).getByRole("button", { name: "添加视频源" });

  for (let index = 1; index < 10; index += 1) {
    await user.click(addButton);
  }

  expect(within(dialog).getAllByTestId("camera-source-editor")).toHaveLength(
    10,
  );
  expect(
    within(dialog).getByRole("button", { name: "上移视频源 1" }),
  ).toBeDisabled();
  expect(
    within(dialog).getByRole("button", { name: "上移视频源 10" }),
  ).toBeEnabled();
  expect(
    within(dialog).getByRole("button", { name: "下移视频源 1" }),
  ).toBeEnabled();
  expect(
    within(dialog).getByRole("button", { name: "下移视频源 10" }),
  ).toBeDisabled();
  expect(dialog.querySelector('[data-slot="scroll-area"]')).toBeInTheDocument();
});

test("重排 Source 后按当前视觉顺序和默认选择提交 POST", async () => {
  let requestBody: CameraCreateRequest | undefined;
  mockServer.use(
    http.post(camerasUrl, async ({ request }) => {
      requestBody = (await request.json()) as CameraCreateRequest;
      // 本用例只验证写请求顺序；返回网络失败可让 Dialog 保持打开，也不会留下成功 Toast 影响后续用例。
      return HttpResponse.error();
    }),
  );
  const { user, dialog } = await openDialog();
  await fillValidCamera(user);
  await user.click(within(dialog).getByRole("button", { name: "添加视频源" }));
  await user.type(within(dialog).getAllByLabelText("名称")[1]!, "子码流");
  await user.type(
    within(dialog).getAllByLabelText("URL 后缀")[1]!,
    "Streaming/Channels/102",
  );
  await user.click(
    within(dialog).getByRole("button", { name: "上移视频源 2" }),
  );
  await user.click(within(dialog).getByRole("radio", { name: /视频源 1/ }));
  await user.click(within(dialog).getByRole("button", { name: "保存摄像头" }));

  await waitFor(() => expect(requestBody).toBeDefined());
  expect(await within(dialog).findByText("创建结果未知")).toBeInTheDocument();
  expect(requestBody?.sources).toEqual([
    {
      name: "子码流",
      url_suffix: "Streaming/Channels/102",
      is_default_preview: true,
    },
    {
      name: "主码流",
      url_suffix: "Streaming/Channels/101",
      is_default_preview: false,
    },
  ]);
});

test("提交期间锁定 Dialog、字段和全部写操作，且请求只发送一次", async () => {
  let finishRequest = () => {};
  const pendingRequest = new Promise<void>((resolve) => {
    finishRequest = resolve;
  });
  let requestCount = 0;
  mockServer.use(
    http.post(camerasUrl, async () => {
      requestCount += 1;
      await pendingRequest;
      return HttpResponse.error();
    }),
  );
  const { user, dialog } = await openDialog();
  await fillValidCamera(user);

  await user.click(within(dialog).getByRole("button", { name: "保存摄像头" }));
  expect(
    await within(dialog).findByRole("button", { name: /正在保存/ }),
  ).toBeDisabled();
  expect(within(dialog).getByLabelText("摄像头名称")).toBeDisabled();
  expect(within(dialog).getByRole("button", { name: "取消" })).toBeDisabled();
  expect(within(dialog).queryByRole("button", { name: "关闭" })).toBeNull();

  await user.keyboard("{Escape}");
  expect(
    screen.getByRole("dialog", { name: "添加摄像头" }),
  ).toBeInTheDocument();
  const overlay = document.querySelector('[data-slot="dialog-overlay"]');
  if (overlay !== null) {
    fireEvent.pointerDown(overlay);
    fireEvent.click(overlay);
  }
  expect(
    screen.getByRole("dialog", { name: "添加摄像头" }),
  ).toBeInTheDocument();
  expect(requestCount).toBe(1);

  act(() => {
    finishRequest();
  });
  expect(await within(dialog).findByText("创建结果未知")).toBeInTheDocument();
});

test("创建成功后关闭并重置、失效 Cameras 前缀且不改变路由", async () => {
  useScenario("success");
  const invalidate = vi.spyOn(queryClient, "invalidateQueries");
  const { user, dialog, router } = await (async () => {
    const user = userEvent.setup();
    const rendered = renderAppRoute("/cameras");
    await user.click(await screen.findByRole("button", { name: "添加摄像头" }));
    return {
      user,
      dialog: await screen.findByRole("dialog", { name: "添加摄像头" }),
      router: rendered.router,
    };
  })();
  await fillValidCamera(user);
  await user.click(within(dialog).getByRole("button", { name: "保存摄像头" }));

  await waitFor(() =>
    expect(screen.queryByRole("dialog", { name: "添加摄像头" })).toBeNull(),
  );
  expect(await screen.findByText("摄像头已创建")).toBeInTheDocument();
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ["cameras"] });
  expect(router.state.location.pathname).toBe("/cameras");
  expect(document.body.textContent).not.toContain(CAMERA_FIXTURE_SECRET);
  await waitFor(() =>
    expect(queryClient.getMutationCache().getAll()).toHaveLength(0),
  );
  expect(
    queryClient.getQueryData(["camera", CAMERA_FIXTURE_IDS.primaryCamera]),
  ).toBeUndefined();
  expect(localStorage).toHaveLength(0);
  expect(sessionStorage).toHaveLength(0);

  await user.click(screen.getByRole("button", { name: "添加摄像头" }));
  expect(await screen.findByLabelText("摄像头名称")).toHaveValue("");
  expect(screen.getByLabelText("RTSP 端口")).toHaveValue(554);
});

test("嵌套 422 按服务端顺序设置字段错误并聚焦第一个现有控件", async () => {
  useScenario("nested-validation-error");
  const { user, dialog } = await openDialog();
  await fillValidCamera(user);
  await user.click(within(dialog).getByRole("button", { name: "添加视频源" }));
  await user.type(within(dialog).getAllByLabelText("名称")[1]!, "备用码流");
  await user.type(
    within(dialog).getAllByLabelText("URL 后缀")[1]!,
    "Streaming/Channels/102",
  );
  await user.click(within(dialog).getByRole("button", { name: "保存摄像头" }));

  expect(
    await within(dialog).findByText("该字段为必填项。"),
  ).toBeInTheDocument();
  expect(
    within(dialog).getByText("规范化后的视频源后缀不能重复。"),
  ).toBeInTheDocument();
  await waitFor(() =>
    expect(within(dialog).getAllByLabelText("名称")[1]).toHaveFocus(),
  );
  expect(within(dialog).getByLabelText("摄像头名称")).toHaveValue("洗手区 01");
});

test.each(["transport", "unexpected", "503"] as const)(
  "%s 错误显示结果未知、保留输入且不自动重发",
  async (kind) => {
    let requestCount = 0;
    if (kind === "503") {
      useScenario("dependency-unavailable");
    } else {
      mockServer.use(
        http.post(camerasUrl, () => {
          requestCount += 1;
          return kind === "transport"
            ? HttpResponse.error()
            : HttpResponse.json(
                { message: "invalid error shape" },
                { status: 500 },
              );
        }),
      );
    }

    const { user, dialog } = await openDialog();
    await fillValidCamera(user);
    await user.click(
      within(dialog).getByRole("button", { name: "保存摄像头" }),
    );

    expect(await within(dialog).findByText("创建结果未知")).toBeInTheDocument();
    expect(
      within(dialog).getByText(/再次保存会发送一条新的创建请求/),
    ).toBeInTheDocument();
    expect(within(dialog).getByLabelText("摄像头名称")).toHaveValue(
      "洗手区 01",
    );
    if (kind !== "503") {
      expect(requestCount).toBe(1);
    }
    expect(document.body.textContent).not.toContain("camera-password");

    if (kind === "transport") {
      await user.click(
        within(dialog).getByRole("button", { name: "保存摄像头" }),
      );
      await waitFor(() => expect(requestCount).toBe(2));
      expect(within(dialog).getByText("创建结果未知")).toBeInTheDocument();
    }
  },
);

test("无法定位的服务端字段错误进入表单级 Alert", async () => {
  mockServer.use(
    http.post(camerasUrl, ({ request }) => {
      const traceId = "tr_unknown_field_path";
      return HttpResponse.json(
        {
          type: "urn:sop-vision:problem:validation-error",
          title: "请求字段验证失败",
          status: 422,
          code: "VALIDATION_ERROR",
          detail: "存在无效字段。",
          instance: new URL(request.url).pathname,
          trace_id: traceId,
          errors: [
            {
              field: "sources[99].name",
              code: "REQUIRED",
              detail: "无法定位的视频源字段错误。",
            },
          ],
          context: {},
        },
        {
          status: 422,
          headers: {
            "Content-Type": "application/problem+json",
            "X-Trace-Id": traceId,
          },
        },
      );
    }),
  );
  const { user, dialog } = await openDialog();
  await fillValidCamera(user);
  await user.click(within(dialog).getByRole("button", { name: "保存摄像头" }));

  expect(
    await within(dialog).findByText("无法定位的视频源字段错误。"),
  ).toBeInTheDocument();
});
