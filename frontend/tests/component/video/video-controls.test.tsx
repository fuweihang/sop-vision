import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import {
  VideoControls,
  type VideoControlsMode,
} from "@/features/video/components/video-controls";
import { VideoSurface } from "@/features/video/components/video-surface";
import type { StreamSessionStatus } from "@/features/video/stream-session/stream-session";
import {
  installFullscreenMocks,
  installMediaElementMocks,
  installPlayingMediaElementMocks,
} from "@/test/media-browser-mocks";

function createPlaybackStream() {
  const audioTrack = {
    id: "audio-1",
    kind: "audio",
    stop: vi.fn(),
  } as unknown as MediaStreamTrack;
  const videoTrack = {
    id: "video-1",
    kind: "video",
    stop: vi.fn(),
  } as unknown as MediaStreamTrack;
  return {
    getTracks: () => [audioTrack, videoTrack],
    getAudioTracks: () => [audioTrack],
    getVideoTracks: () => [videoTrack],
  } as unknown as MediaStream;
}

function renderControls({
  status = "playing",
  stream = createPlaybackStream(),
  onReconnect = vi.fn(),
  mode = "interactive",
}: {
  status?: StreamSessionStatus;
  stream?: MediaStream | null;
  onReconnect?: () => void;
  mode?: VideoControlsMode;
} = {}) {
  return {
    ...render(
      <TooltipProvider>
        <VideoSurface stream={stream} objectFit="contain">
          <VideoControls
            status={status}
            onReconnect={onReconnect}
            mode={mode}
          />
        </VideoSurface>
      </TooltipProvider>,
    ),
    onReconnect,
    stream,
  };
}

test("操作栏支持播放暂停、刷新、音量浮层和全屏切换", async () => {
  const user = userEvent.setup();
  const { play, pause } = installPlayingMediaElementMocks();
  const { requestFullscreen, exitFullscreen } = installFullscreenMocks();
  const { onReconnect } = renderControls();
  const video = screen.getByLabelText<HTMLVideoElement>("实时视频");
  const controls = screen.getByRole("toolbar", { name: "视频操作" });

  expect(screen.getByText("正在加载")).toBeVisible();
  expect(screen.queryByText("LIVE")).not.toBeInTheDocument();
  fireEvent.loadedData(video);
  expect(await screen.findByText("LIVE")).toBeVisible();
  expect(controls).toHaveClass("opacity-0", "pointer-events-none");
  fireEvent.pointerMove(
    screen.getByRole("group", { name: "视频播放器控制层" }),
    { pointerType: "mouse" },
  );
  expect(controls).toHaveClass("opacity-100", "pointer-events-auto");

  await user.click(screen.getByRole("button", { name: "暂停" }));
  expect(pause).toHaveBeenCalledOnce();
  // 暂停由播放按钮表达；已经出画的视频仍保持 LIVE，不改写连接/出画状态。
  expect(screen.getByText("LIVE")).toBeVisible();
  expect(screen.getByRole("button", { name: "播放" })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
  await user.click(screen.getByRole("button", { name: "播放" }));
  expect(play).toHaveBeenCalledTimes(2);

  await user.click(screen.getByRole("button", { name: "刷新当前流" }));
  expect(onReconnect).toHaveBeenCalledOnce();

  expect(video.muted).toBe(true);
  expect(video.volume).toBe(0);
  const volumeButton = screen.getByRole("button", { name: "取消静音" });
  expect(screen.queryByRole("group", { name: "音量" })).not.toBeInTheDocument();
  fireEvent.click(volumeButton);
  expect(screen.queryByRole("group", { name: "音量" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "静音" }));
  expect(screen.queryByRole("group", { name: "音量" })).not.toBeInTheDocument();

  fireEvent.mouseEnter(volumeButton);
  const volumeSlider = await screen.findByRole("group", { name: "音量" });
  expect(volumeSlider).toHaveAttribute("data-orientation", "vertical");
  expect(screen.queryByText("0%")).not.toBeInTheDocument();
  expect(volumeSlider).toHaveAttribute("data-volume-percent", "0");
  await user.click(volumeButton);
  expect(video.muted).toBe(false);
  expect(video.volume).toBe(0.7);
  expect(volumeButton).toHaveAttribute("aria-expanded", "true");
  expect(volumeSlider).toBeVisible();
  expect(volumeSlider).toHaveAttribute("data-volume-percent", "70");

  await user.click(screen.getByRole("button", { name: "静音" }));
  expect(video.muted).toBe(true);
  expect(video.volume).toBe(0);
  expect(volumeButton).toHaveAttribute("aria-expanded", "true");
  expect(volumeSlider).toBeVisible();
  expect(volumeSlider).toHaveAttribute("data-volume-percent", "0");

  await user.click(screen.getByRole("button", { name: "进入浏览器全屏" }));
  expect(requestFullscreen).toHaveBeenCalledOnce();
  // Base UI 关闭动画结束后可能重建 Portal；全屏后重新读取当前可见 Slider，不能断言旧节点。
  const fullscreenContainer = video.parentElement;
  if (fullscreenContainer === null) {
    throw new Error("实时视频缺少全屏容器。");
  }
  expect(
    await within(fullscreenContainer).findByRole("group", { name: "音量" }),
  ).toBeVisible();
  await user.click(screen.getByRole("button", { name: "退出浏览器全屏" }));
  expect(exitFullscreen).toHaveBeenCalledOnce();
});

test("仅禁用媒体控件时仍按当前 video 的出画结果显示 loading 和 LIVE", () => {
  installMediaElementMocks();
  renderControls({ mode: "read-only" });

  expect(screen.getByText("正在加载")).toBeVisible();
  expect(screen.queryByText("已停止")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /^(播放|暂停)$/ })).toBeDisabled();
  expect(screen.getByRole("button", { name: "刷新当前流" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "取消静音" })).toBeDisabled();

  fireEvent.loadedData(screen.getByLabelText("实时视频"));
  expect(screen.getByText("LIVE")).toBeVisible();
});

test("interactive 模式的 Session 失败提示可以刷新当前流", () => {
  installMediaElementMocks();
  const onReconnect = vi.fn();
  renderControls({
    status: "failed",
    stream: null,
    onReconnect,
    mode: "interactive",
  });

  const alert = screen.getByRole("alert");
  expect(within(alert).getByText("视频连接失败，请刷新当前流。")).toBeVisible();
  fireEvent.click(within(alert).getByRole("button", { name: "刷新当前流" }));
  expect(onReconnect).toHaveBeenCalledOnce();
});

test("read-only 模式的播放受阻只显示错误文字", async () => {
  installMediaElementMocks({
    play: () => Promise.reject(new Error("blocked")),
  });
  renderControls({ mode: "read-only" });

  const alert = await screen.findByRole("alert");
  expect(
    within(alert).getByText("浏览器阻止了自动播放，请手动继续。"),
  ).toBeVisible();
  expect(
    within(alert).queryByRole("button", { name: "继续播放" }),
  ).not.toBeInTheDocument();
});

test("read-only 模式的画面超时只显示错误文字", async () => {
  vi.useFakeTimers();
  try {
    installMediaElementMocks();
    renderControls({ mode: "read-only" });

    await act(() => vi.advanceTimersByTimeAsync(10_000));
    const alert = screen.getByRole("alert");
    expect(
      within(alert).getByText("视频画面加载超时，请刷新当前流。"),
    ).toBeVisible();
    expect(
      within(alert).queryByRole("button", { name: "刷新当前流" }),
    ).not.toBeInTheDocument();
  } finally {
    vi.useRealTimers();
  }
});

test("read-only 模式的 Session 失败只显示错误文字", () => {
  installMediaElementMocks();
  renderControls({ status: "failed", stream: null, mode: "read-only" });

  const alert = screen.getByRole("alert");
  expect(within(alert).getByText("视频连接失败，请刷新当前流。")).toBeVisible();
  expect(
    within(alert).queryByRole("button", { name: "刷新当前流" }),
  ).not.toBeInTheDocument();
});

test("stopped 模式优先显示已停止并隐藏旧 Session 错误", () => {
  installMediaElementMocks();
  renderControls({ status: "failed", stream: null, mode: "stopped" });

  expect(screen.getByText("已停止")).toBeVisible();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "刷新当前流" })).toBeDisabled();
});

test("自动播放失败提示不随操作栏隐藏", async () => {
  installMediaElementMocks({
    play: () => Promise.reject(new Error("blocked")),
  });
  renderControls();

  const errorMessage =
    await screen.findByText("浏览器阻止了自动播放，请手动继续。");
  expect(errorMessage).toBeVisible();
  expect(screen.getByText("播放受阻")).toBeVisible();
  expect(screen.getByRole("toolbar", { name: "视频操作" })).toHaveClass(
    "opacity-0",
  );
  expect(screen.getByRole("button", { name: "继续播放" })).toBeVisible();
});

test("连接期间显示 loading 且音量按钮常驻", () => {
  installMediaElementMocks();

  const rendered = renderControls({ status: "connecting", stream: null });

  expect(screen.getByText("正在加载视频")).toBeVisible();
  expect(screen.getByRole("status", { name: "正在加载" })).toBeVisible();
  expect(screen.getByRole("button", { name: "取消静音" })).toBeEnabled();

  rendered.rerender(
    <TooltipProvider>
      <VideoSurface stream={null} objectFit="contain">
        <VideoControls
          status="reconnecting"
          onReconnect={vi.fn()}
          mode="interactive"
        />
      </VideoSurface>
    </TooltipProvider>,
  );
  expect(screen.getByText("正在重新连接视频")).toBeVisible();
});

test("连接状态变为 playing 后继续等待首帧，loadeddata 降级事件到达后结束 loading", () => {
  installMediaElementMocks();
  renderControls();

  expect(screen.getByText("正在加载视频")).toBeVisible();
  expect(screen.getByText("正在加载")).toBeVisible();
  expect(screen.queryByText("LIVE")).not.toBeInTheDocument();
  fireEvent.loadedData(screen.getByLabelText("实时视频"));
  expect(screen.queryByText("正在加载视频")).not.toBeInTheDocument();
  expect(screen.getByText("LIVE")).toBeVisible();
});

test("首帧前暂停时隐藏 loading 并停止超时，继续播放后恢复等待", async () => {
  vi.useFakeTimers();
  try {
    installPlayingMediaElementMocks();
    renderControls();

    expect(screen.getByText("正在加载视频")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "暂停" }));
    expect(screen.getByText("等待画面")).toBeVisible();
    expect(screen.queryByText("正在加载视频")).not.toBeInTheDocument();

    // VideoSurface 暂停首帧计时；即使时间经过也不能把用户主动暂停误报成解码超时。
    await act(() => vi.advanceTimersByTimeAsync(10_000));
    expect(screen.queryByText("画面超时")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "播放" }));
    await act(() => Promise.resolve());
    expect(screen.getByText("正在加载")).toBeVisible();
    expect(screen.getByText("正在加载视频")).toBeVisible();

    await act(() => vi.advanceTimersByTimeAsync(10_000));
    expect(screen.getByText("画面超时")).toBeVisible();
  } finally {
    vi.useRealTimers();
  }
});

test("播放状态下十秒没有首帧时结束 loading 并允许刷新当前流", async () => {
  vi.useFakeTimers();
  installMediaElementMocks();
  const onReconnect = vi.fn();
  renderControls({ onReconnect });

  expect(screen.getByText("正在加载视频")).toBeVisible();
  await act(() => vi.advanceTimersByTimeAsync(10_000));
  expect(screen.queryByText("正在加载视频")).not.toBeInTheDocument();
  expect(screen.getByText("画面超时")).toBeVisible();
  expect(screen.getByText("视频画面加载超时，请刷新当前流。")).toBeVisible();
  fireEvent.click(
    within(screen.getByRole("alert")).getByRole("button", {
      name: "刷新当前流",
    }),
  );
  expect(onReconnect).toHaveBeenCalledOnce();

  vi.useRealTimers();
});

test("全屏切换重试成功后清除上一次失败提示", async () => {
  const user = userEvent.setup();
  installMediaElementMocks();
  const { requestFullscreen } = installFullscreenMocks();
  requestFullscreen.mockRejectedValueOnce(new Error("临时拒绝"));
  renderControls();

  await user.click(screen.getByRole("button", { name: "进入浏览器全屏" }));
  expect(await screen.findByText("无法切换浏览器全屏，请重试。")).toBeVisible();

  await user.click(screen.getByRole("button", { name: "进入浏览器全屏" }));
  await waitFor(() =>
    expect(
      screen.queryByText("无法切换浏览器全屏，请重试。"),
    ).not.toBeInTheDocument(),
  );
  expect(screen.getByRole("button", { name: "退出浏览器全屏" })).toBeEnabled();
});

test("网页全屏和浏览器全屏互斥且不替换 video DOM", async () => {
  const user = userEvent.setup();
  installMediaElementMocks();
  const { requestFullscreen, exitFullscreen } = installFullscreenMocks();
  const { unmount } = renderControls();
  const video = screen.getByLabelText("实时视频");

  await user.click(screen.getByRole("button", { name: "进入网页全屏" }));
  expect(document.body.style.overflow).toBe("hidden");
  expect(screen.getByRole("button", { name: "退出网页全屏" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  await user.click(screen.getByRole("button", { name: "进入浏览器全屏" }));
  expect(requestFullscreen).toHaveBeenCalledOnce();
  expect(document.body.style.overflow).toBe("");
  expect(video.parentElement).not.toHaveClass("fixed");
  expect(screen.getByLabelText("实时视频")).toBe(video);

  await user.click(screen.getByRole("button", { name: "进入网页全屏" }));
  expect(exitFullscreen).toHaveBeenCalledOnce();
  expect(document.body.style.overflow).toBe("hidden");
  expect(screen.getByLabelText("实时视频")).toBe(video);

  await user.click(screen.getByRole("button", { name: "退出网页全屏" }));
  expect(document.body.style.overflow).toBe("");

  await user.click(screen.getByRole("button", { name: "进入网页全屏" }));
  unmount();
  expect(document.body.style.overflow).toBe("");
});
