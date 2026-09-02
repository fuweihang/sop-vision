import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";

import { CameraDetailView } from "@/features/cameras/components/camera-detail-view";
import { renderWithStreamSession } from "@/features/cameras/testing/render-with-stream-session";
import {
  buildCameraDetail,
  CAMERA_FIXTURE_IDS,
} from "@/mocks/cameras/fixtures";
import { installFullscreenMocks } from "@/test/media-browser-mocks";

test("默认 Source 无法匹配时显示损坏响应错误且不 acquire", () => {
  const camera = buildCameraDetail();
  const invalidCamera = {
    ...camera,
    default_preview_source_id: CAMERA_FIXTURE_IDS.tertiarySource,
  };
  const { fakeStreamSessions } = renderWithStreamSession(
    <CameraDetailView camera={invalidCamera} />,
  );

  expect(screen.getByText("默认预览源无效")).toBeVisible();
  expect(screen.queryByRole("region", { name: "视频源预览" })).toBeNull();
  expect(fakeStreamSessions).toHaveLength(0);
});

test("停止意图跨详情刷新和默认 Source 改变保留，再次开始才连接最新默认源", async () => {
  const user = userEvent.setup();
  const initialCamera = buildCameraDetail({
    sources: [
      { status: "ONLINE" },
      {
        status: "ONLINE",
        whep_url: "https://media.example.invalid/secondary/whep",
      },
    ],
  });
  const result = renderWithStreamSession(
    <CameraDetailView camera={initialCamera} />,
  );
  await waitFor(() => expect(result.fakeStreamSessions).toHaveLength(1));

  await user.click(screen.getByRole("button", { name: "停止预览" }));
  await act(() => Promise.resolve());
  expect(result.streamSessionManager.activeSessionCount).toBe(0);
  expect(screen.getByText("预览已停止")).toBeVisible();

  result.rerender(
    <CameraDetailView camera={{ ...initialCamera, name: "刷新后的摄像头" }} />,
  );
  expect(screen.getByRole("button", { name: "开始预览" })).toBeEnabled();
  expect(result.fakeStreamSessions).toHaveLength(1);

  const changedDefaultCamera = buildCameraDetail({
    sources: [
      { status: "ONLINE" },
      {
        status: "ONLINE",
        whep_url: "https://media.example.invalid/secondary/whep",
      },
    ],
    defaultSourceIndex: 1,
  });
  result.rerender(<CameraDetailView camera={changedDefaultCamera} />);
  await act(() => Promise.resolve());
  expect(result.fakeStreamSessions).toHaveLength(1);
  expect(screen.getByRole("button", { name: "开始预览" })).toBeEnabled();
  expect(result.streamSessionManager.activeSessionCount).toBe(0);

  await user.click(screen.getByRole("button", { name: "开始预览" }));
  await waitFor(() => expect(result.fakeStreamSessions).toHaveLength(2));
  expect(result.acquiredWhepUrls[1]).toBe(
    changedDefaultCamera.sources[1]?.whep_url,
  );

  // 已重新开始后，default 选择会继续跟随 Backend 默认源变化。
  result.rerender(<CameraDetailView camera={initialCamera} />);
  await waitFor(() => expect(result.fakeStreamSessions).toHaveLength(3));
  expect(screen.getByRole("button", { name: "停止预览" })).toBeEnabled();
  expect(result.streamSessionManager.activeSessionCount).toBe(1);
});

test("默认 Source 的 WHEP 入口恢复后按原有预览意图自动开始", async () => {
  const unavailableCamera = buildCameraDetail({
    sources: [
      { status: "OFFLINE", whep_url: null },
      { status: "ONLINE", whep_url: null },
    ],
  });
  const result = renderWithStreamSession(
    <CameraDetailView camera={unavailableCamera} />,
  );

  expect(screen.getByText("当前视频源不可播放")).toBeVisible();
  expect(screen.getByRole("button", { name: "开始预览" })).toBeDisabled();
  expect(result.fakeStreamSessions).toHaveLength(0);

  result.rerender(<CameraDetailView camera={buildCameraDetail()} />);
  await waitFor(() => expect(result.fakeStreamSessions).toHaveLength(1));
  expect(screen.getByRole("button", { name: "停止预览" })).toBeEnabled();
});

test("默认 Source 不可播放时连接响应顺序中的第一路可播放 Source", async () => {
  const camera = buildCameraDetail({
    sources: [
      { status: "OFFLINE", whep_url: null },
      { status: "ONLINE" },
      { status: "ONLINE" },
    ],
  });
  const result = renderWithStreamSession(<CameraDetailView camera={camera} />);

  await waitFor(() => expect(result.fakeStreamSessions).toHaveLength(1));
  expect(result.acquiredWhepUrls[0]).toBe(camera.sources[1]?.whep_url);
  expect(
    screen.getByRole("combobox", { name: "切换预览源" }),
  ).toHaveTextContent(camera.sources[1]?.name ?? "");
});

test("长 Source 名称在控制栏和弹层内保持单行省略", async () => {
  const user = userEvent.setup();
  const longChineseName = "视频".repeat(64);
  const longAsciiName = "A".repeat(128);
  const camera = buildCameraDetail({
    sources: [
      { name: longChineseName, status: "ONLINE" },
      { name: longAsciiName, status: "ONLINE" },
    ],
  });
  renderWithStreamSession(<CameraDetailView camera={camera} />);

  const trigger = screen.getByRole("combobox", { name: "切换预览源" });
  const selectedValue = trigger.querySelector("[data-slot='select-value']");
  expect(trigger).toHaveClass(
    "w-fit",
    "max-w-36",
    "overflow-hidden",
    "**:data-[slot=select-value]:block",
    "**:data-[slot=select-value]:min-w-0",
    "**:data-[slot=select-value]:truncate",
    "[&>svg]:shrink-0",
  );
  expect(selectedValue).toHaveAttribute("title", longChineseName);

  await user.click(trigger);

  const listbox = await screen.findByRole("listbox");
  const content = listbox.closest("[data-slot='select-content']");
  const chineseOption = screen.getByRole("option", { name: longChineseName });
  const asciiOption = screen.getByRole("option", { name: longAsciiName });
  const chineseName = chineseOption.querySelector(
    `[title="${longChineseName}"]`,
  );
  const asciiName = asciiOption.querySelector(`[title="${longAsciiName}"]`);
  const itemText = asciiOption.querySelector(":scope > div");

  expect(content).toHaveClass("max-w-(--available-width)");
  expect(asciiOption).toHaveClass(
    "min-w-0",
    "overflow-hidden",
    "[&>div]:min-w-0",
    "[&>div]:shrink",
    "[&>div]:overflow-hidden",
  );
  expect(itemText?.tagName).toBe("DIV");
  expect(itemText).toHaveClass("shrink-0", "whitespace-nowrap");
  expect(chineseName).toHaveClass("min-w-0", "flex-1", "truncate");
  expect(asciiName).toHaveClass("min-w-0", "flex-1", "truncate");

  // Base UI 关闭浮层时会执行退出过渡；显式等待清理，避免 Portal 状态影响后续用例。
  await user.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull());
});

test("临时切源释放旧 Session，刷新时保留，Source 失效后回到默认源", async () => {
  const user = userEvent.setup();
  const camera = buildCameraDetail({
    sources: [
      { name: "主码流", status: "ONLINE" },
      { name: "子码流", status: "ONLINE" },
      { name: "离线流", status: "OFFLINE", whep_url: null },
    ],
  });
  const temporarySource = camera.sources[1];
  if (temporarySource === undefined) {
    throw new Error("测试 Camera 缺少临时 Source。");
  }
  const result = renderWithStreamSession(<CameraDetailView camera={camera} />);
  await waitFor(() => expect(result.fakeStreamSessions).toHaveLength(1));

  await user.click(screen.getByRole("combobox", { name: "切换预览源" }));
  expect(await screen.findByRole("option", { name: /离线流/ })).toHaveAttribute(
    "aria-disabled",
    "true",
  );
  await user.click(screen.getByRole("option", { name: /子码流/ }));

  await waitFor(() => expect(result.fakeStreamSessions).toHaveLength(2));
  expect(result.fakeStreamSessions[0]?.closeCount).toBe(1);
  expect(result.acquiredWhepUrls[1]).toBe(temporarySource.whep_url);
  expect(
    screen.getByRole("combobox", { name: "切换预览源" }),
  ).toHaveTextContent("子码流");

  result.rerender(
    <CameraDetailView camera={{ ...camera, name: "普通刷新后的名称" }} />,
  );
  await act(() => Promise.resolve());
  expect(result.fakeStreamSessions).toHaveLength(2);
  expect(
    screen.getByRole("combobox", { name: "切换预览源" }),
  ).toHaveTextContent("子码流");

  const offlineSource = camera.sources[2];
  if (offlineSource === undefined) {
    throw new Error("测试 Camera 缺少离线 Source。");
  }
  const changedBackendDefault = {
    ...camera,
    default_preview_source_id: offlineSource.source_id,
    sources: camera.sources.map((source) => ({
      ...source,
      is_default_preview: source.source_id === offlineSource.source_id,
    })),
  };
  result.rerender(<CameraDetailView camera={changedBackendDefault} />);
  await act(() => Promise.resolve());
  expect(result.fakeStreamSessions).toHaveLength(2);
  expect(result.fakeStreamSessions[1]?.closeCount).toBe(0);
  expect(
    screen.getByRole("combobox", { name: "切换预览源" }),
  ).toHaveTextContent("子码流");

  const temporaryUnavailable = {
    ...changedBackendDefault,
    sources: changedBackendDefault.sources.map((source) =>
      source.source_id === temporarySource.source_id
        ? { ...source, status: "OFFLINE" as const, whep_url: null }
        : source,
    ),
  };
  result.rerender(<CameraDetailView camera={temporaryUnavailable} />);
  await waitFor(() => expect(result.fakeStreamSessions).toHaveLength(3));
  expect(result.fakeStreamSessions[1]?.closeCount).toBe(1);
  expect(result.acquiredWhepUrls[2]).toBe(camera.sources[0]?.whep_url);
  expect(
    screen.getByRole("combobox", { name: "切换预览源" }),
  ).toHaveTextContent("主码流");
});

test("停止预览时允许选择 Source，但再次开始前不 acquire", async () => {
  const user = userEvent.setup();
  const camera = buildCameraDetail({
    sources: [
      { name: "主码流", status: "ONLINE" },
      { name: "子码流", status: "ONLINE" },
    ],
  });
  const result = renderWithStreamSession(<CameraDetailView camera={camera} />);
  await waitFor(() => expect(result.fakeStreamSessions).toHaveLength(1));

  await user.click(screen.getByRole("button", { name: "停止预览" }));
  await act(() => Promise.resolve());
  expect(result.streamSessionManager.activeSessionCount).toBe(0);

  await user.click(screen.getByRole("combobox", { name: "切换预览源" }));
  await user.click(await screen.findByRole("option", { name: /子码流/ }));
  await act(() => Promise.resolve());
  expect(result.fakeStreamSessions).toHaveLength(1);

  await user.click(screen.getByRole("button", { name: "开始预览" }));
  await waitFor(() => expect(result.fakeStreamSessions).toHaveLength(2));
  expect(result.acquiredWhepUrls[1]).toBe(camera.sources[1]?.whep_url);
});

test("浏览器全屏时 Source Select 留在播放器容器内且打开期间保持操作栏显示", async () => {
  const user = userEvent.setup();
  installFullscreenMocks();
  const camera = buildCameraDetail({
    sources: [
      { name: "主码流", status: "ONLINE" },
      { name: "子码流", status: "ONLINE" },
    ],
  });
  renderWithStreamSession(<CameraDetailView camera={camera} />);

  await user.click(screen.getByRole("button", { name: "进入浏览器全屏" }));
  await user.click(screen.getByRole("combobox", { name: "切换预览源" }));

  const videoContainer = screen.getByLabelText("实时视频").parentElement;
  const listbox = await screen.findByRole("listbox");
  expect(videoContainer).not.toBeNull();
  expect(videoContainer?.contains(listbox)).toBe(true);
  expect(screen.getByRole("toolbar", { name: "视频操作" })).toHaveClass(
    "opacity-100",
  );
});
