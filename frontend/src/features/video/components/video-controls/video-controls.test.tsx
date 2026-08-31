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
import { VideoControls } from "@/features/video/components/video-controls";
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
}: {
  status?: StreamSessionStatus;
  stream?: MediaStream | null;
  onReconnect?: () => void;
} = {}) {
  return {
    ...render(
      <TooltipProvider>
        <VideoSurface stream={stream} objectFit="contain">
          <VideoControls status={status} onReconnect={onReconnect} />
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

  expect(await screen.findByText("LIVE")).toBeVisible();
  expect(controls).toHaveClass("opacity-0", "pointer-events-none");
  fireEvent.pointerMove(
    screen.getByRole("group", { name: "视频播放器控制层" }),
    { pointerType: "mouse" },
  );
  expect(controls).toHaveClass("opacity-100", "pointer-events-auto");

  await user.click(screen.getByRole("button", { name: "暂停" }));
  expect(pause).toHaveBeenCalledOnce();
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
  expect(volumeSlider).toHaveClass("h-20");
  expect(volumeSlider.closest('[data-slot="popover-content"]')).toHaveClass(
    "w-fit",
    "min-w-0",
    "p-1.5",
  );
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
    within(fullscreenContainer).getByRole("group", { name: "音量" }),
  ).toBeVisible();
  await user.click(screen.getByRole("button", { name: "退出浏览器全屏" }));
  expect(exitFullscreen).toHaveBeenCalledOnce();
});

test("点击静音恢复静音前音量，Slider 归零后恢复默认 70%", async () => {
  const user = userEvent.setup();
  installMediaElementMocks();
  renderControls();

  const video = screen.getByLabelText<HTMLVideoElement>("实时视频");
  const volumeButton = screen.getByRole("button", { name: "取消静音" });
  fireEvent.mouseEnter(volumeButton);
  const volumeSlider = await screen.findByRole("group", { name: "音量" });
  const volumeSliderInput = volumeSlider.querySelector<HTMLInputElement>(
    'input[type="range"]',
  );
  expect(volumeSliderInput).not.toBeNull();
  if (volumeSliderInput === null) {
    throw new Error("音量 Slider 缺少内部 range input。");
  }

  await user.click(volumeButton);
  expect(video.muted).toBe(false);
  expect(video.volume).toBe(0.7);

  fireEvent.change(volumeSliderInput, { target: { value: "40" } });
  expect(video.volume).toBe(0.4);
  await user.click(screen.getByRole("button", { name: "静音" }));
  expect(video.muted).toBe(true);
  expect(video.volume).toBe(0);
  await user.click(screen.getByRole("button", { name: "取消静音" }));
  expect(video.muted).toBe(false);
  expect(video.volume).toBe(0.4);

  fireEvent.change(volumeSliderInput, { target: { value: "0" } });
  expect(video.muted).toBe(true);
  expect(video.volume).toBe(0);
  await user.click(screen.getByRole("button", { name: "取消静音" }));
  expect(video.muted).toBe(false);
  expect(video.volume).toBe(0.7);
});

test("鼠标无活动后隐藏操作栏，连接失败文字仍保持可见", () => {
  vi.useFakeTimers();
  installMediaElementMocks();
  renderControls({ status: "failed" });
  const layer = screen.getByRole("group", { name: "视频播放器控制层" });
  const controls = screen.getByRole("toolbar", { name: "视频操作" });

  fireEvent.pointerMove(layer, { pointerType: "mouse" });
  expect(controls).toHaveClass("opacity-100");
  void act(() => vi.advanceTimersByTime(2_500));
  expect(controls).toHaveClass("opacity-0", "pointer-events-none");
  expect(screen.getByText("视频连接失败，请刷新当前流。")).toBeVisible();

  vi.useRealTimers();
});

test("自动播放失败提示不随操作栏隐藏且长文本不会挤压操作按钮", async () => {
  installMediaElementMocks({
    play: () => Promise.reject(new Error("blocked")),
  });
  renderControls();

  const errorMessage =
    await screen.findByText("浏览器阻止了自动播放，请手动继续。");
  expect(errorMessage).toBeVisible();
  // Alert 默认带 w-full；绝对定位时必须覆盖为 auto，左右 inset 才能同时保留边距。
  expect(screen.getByRole("alert")).toHaveClass("inset-x-3", "w-auto");
  expect(errorMessage).toHaveClass("min-w-0", "flex-1", "wrap-anywhere");
  expect(errorMessage.parentElement).toHaveClass("flex-col", "@md:flex-row");
  expect(screen.getByRole("toolbar", { name: "视频操作" })).toHaveClass(
    "opacity-0",
  );
  expect(screen.getByRole("button", { name: "继续播放" })).toHaveClass(
    "self-start",
    "@md:self-auto",
  );
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
        <VideoControls status="reconnecting" onReconnect={vi.fn()} />
      </VideoSurface>
    </TooltipProvider>,
  );
  expect(screen.getByText("正在重新连接视频")).toBeVisible();
});

test("连接状态变为 playing 后继续等待首帧，loadeddata 降级事件到达后结束 loading", () => {
  installMediaElementMocks();
  renderControls();

  expect(screen.getByText("正在加载视频")).toBeVisible();
  fireEvent.loadedData(screen.getByLabelText("实时视频"));
  expect(screen.queryByText("正在加载视频")).not.toBeInTheDocument();
});

test("播放状态下十秒没有首帧时结束 loading 并允许刷新当前流", async () => {
  vi.useFakeTimers();
  installMediaElementMocks();
  const onReconnect = vi.fn();
  renderControls({ onReconnect });

  expect(screen.getByText("正在加载视频")).toBeVisible();
  await act(() => vi.advanceTimersByTimeAsync(10_000));
  expect(screen.queryByText("正在加载视频")).not.toBeInTheDocument();
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
  expect(video.parentElement).toHaveClass("fixed", "inset-0", "h-svh");
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
