import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import {
  useVideoSurface,
  VideoSurface,
} from "@/features/video/components/video-surface";
import {
  installFullscreenMocks,
  installMediaElementMocks,
  installPlayingMediaElementMocks,
  installVideoFrameCallbackMocks,
} from "@/test/media-browser-mocks";

function createStream() {
  const stop = vi.fn();
  const audioTrack = {
    id: "audio-1",
    kind: "audio",
    stop,
  } as unknown as MediaStreamTrack;
  const videoTrack = {
    id: "video-1",
    kind: "video",
    stop: vi.fn(),
  } as unknown as MediaStreamTrack;
  const stream = {
    getTracks: () => [audioTrack, videoTrack],
    getAudioTracks: () => [audioTrack],
    getVideoTracks: () => [videoTrack],
  } as unknown as MediaStream;
  return { stream, stop };
}

function FirstFrameProbe() {
  const { state } = useVideoSurface();
  return <output>{state.hasPresentedFrame ? "已有首帧" : "等待首帧"}</output>;
}

function SurfaceProbe() {
  const { state } = useVideoSurface();
  return (
    <output>
      {state.sourceSize.width}×{state.sourceSize.height};
      {state.containerSize.width}×{state.containerSize.height};
      {state.renderedMediaRect.y}
    </output>
  );
}

function SurfaceStateProbe() {
  const { state, actions } = useVideoSurface();

  return (
    <div>
      <output aria-label="媒体状态">
        {state.paused ? "已暂停" : "正在播放"};
        {state.isFullscreen ? "全屏" : "默认"};{state.muted ? "静音" : "有声"};
        {Math.round(state.volume * 100)}
      </output>
      <button type="button" onClick={() => void actions.togglePlayback()}>
        切换播放
      </button>
      <button type="button" onClick={() => void actions.toggleFullscreen()}>
        切换全屏
      </button>
      <button type="button" onClick={() => actions.setMuted(false)}>
        取消静音
      </button>
      <button type="button" onClick={() => actions.setVolume(0.35)}>
        设置音量
      </button>
    </div>
  );
}

test("绑定并清空 srcObject，通过 children Context 提供通用测量值", async () => {
  const { play } = installMediaElementMocks();
  const rect = vi
    .spyOn(HTMLElement.prototype, "getBoundingClientRect")
    .mockReturnValue({
      width: 1000,
      height: 1000,
    } as DOMRect);
  const { stream, stop } = createStream();
  const rendered = render(
    <VideoSurface stream={stream} objectFit="contain">
      <SurfaceProbe />
    </VideoSurface>,
  );
  const video = screen.getByLabelText<HTMLVideoElement>("实时视频");
  Object.defineProperties(video, {
    videoWidth: { configurable: true, value: 1920 },
    videoHeight: { configurable: true, value: 1080 },
  });
  fireEvent.loadedMetadata(video);

  expect(await screen.findByText("1920×1080;1000×1000;218.75")).toBeVisible();
  expect(video.srcObject).toBe(stream);
  expect(play).toHaveBeenCalled();

  rendered.unmount();
  expect(video.srcObject).toBeNull();
  expect(stop).not.toHaveBeenCalled();
  rect.mockRestore();
});

test("通过原生媒体和全屏事件发布实际播放状态", async () => {
  const user = userEvent.setup();
  const { play, pause } = installPlayingMediaElementMocks();
  const { requestFullscreen, exitFullscreen } = installFullscreenMocks();
  const { stream } = createStream();

  render(
    <VideoSurface stream={stream} objectFit="contain">
      <SurfaceStateProbe />
    </VideoSurface>,
  );

  expect(await screen.findByText("正在播放;默认;静音;0")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "切换播放" }));
  expect(screen.getByText("已暂停;默认;静音;0")).toBeVisible();
  expect(pause).toHaveBeenCalledOnce();

  await user.click(screen.getByRole("button", { name: "切换播放" }));
  expect(screen.getByText("正在播放;默认;静音;0")).toBeVisible();
  expect(play).toHaveBeenCalledTimes(2);

  await user.click(screen.getByRole("button", { name: "取消静音" }));
  await user.click(screen.getByRole("button", { name: "设置音量" }));
  expect(screen.getByText("正在播放;默认;有声;35")).toBeVisible();

  await user.click(screen.getByRole("button", { name: "切换全屏" }));
  expect(screen.getByText("正在播放;全屏;有声;35")).toBeVisible();
  expect(requestFullscreen).toHaveBeenCalledOnce();
  await user.click(screen.getByRole("button", { name: "切换全屏" }));
  expect(screen.getByText("正在播放;默认;有声;35")).toBeVisible();
  expect(exitFullscreen).toHaveBeenCalledOnce();
});

test("更换 Stream 时保留用户的播放或暂停意图", async () => {
  const user = userEvent.setup();
  const { play } = installPlayingMediaElementMocks();
  const first = createStream().stream;
  const second = createStream().stream;
  const third = createStream().stream;
  const rendered = render(
    <VideoSurface stream={first} objectFit="contain">
      <SurfaceStateProbe />
    </VideoSurface>,
  );

  expect(await screen.findByText("正在播放;默认;静音;0")).toBeVisible();
  // 刷新停止旧 Track 时浏览器可能先发 pause；它不是用户点击暂停，不能改变播放意图。
  fireEvent.pause(screen.getByLabelText("实时视频"));
  expect(screen.getByText("正在播放;默认;静音;0")).toBeVisible();
  rendered.rerender(
    <VideoSurface stream={null} objectFit="contain">
      <SurfaceStateProbe />
    </VideoSurface>,
  );
  expect(screen.getByText("正在播放;默认;静音;0")).toBeVisible();
  rendered.rerender(
    <VideoSurface stream={second} objectFit="contain">
      <SurfaceStateProbe />
    </VideoSurface>,
  );
  expect(await screen.findByText("正在播放;默认;静音;0")).toBeVisible();
  expect(play).toHaveBeenCalledTimes(2);

  await user.click(screen.getByRole("button", { name: "切换播放" }));
  expect(screen.getByText("已暂停;默认;静音;0")).toBeVisible();
  rendered.rerender(
    <VideoSurface stream={null} objectFit="contain">
      <SurfaceStateProbe />
    </VideoSurface>,
  );
  expect(screen.getByText("已暂停;默认;静音;0")).toBeVisible();
  rendered.rerender(
    <VideoSurface stream={third} objectFit="contain">
      <SurfaceStateProbe />
    </VideoSurface>,
  );
  expect(screen.getByText("已暂停;默认;静音;0")).toBeVisible();
  expect(play).toHaveBeenCalledTimes(2);
});

test("只接受当前 Stream 的视频帧回调，并在换流时重新等待首帧", () => {
  const { callbacks, requestVideoFrameCallback, cancelVideoFrameCallback } =
    installVideoFrameCallbackMocks();
  installMediaElementMocks();
  const first = createStream().stream;
  const second = createStream().stream;
  const rendered = render(
    <VideoSurface stream={first} objectFit="contain">
      <FirstFrameProbe />
    </VideoSurface>,
  );

  expect(screen.getByText("等待首帧")).toBeVisible();
  expect(requestVideoFrameCallback).toHaveBeenCalledOnce();
  rendered.rerender(
    <VideoSurface stream={second} objectFit="contain">
      <FirstFrameProbe />
    </VideoSurface>,
  );
  expect(cancelVideoFrameCallback).toHaveBeenCalledWith(1);
  expect(requestVideoFrameCallback).toHaveBeenCalledTimes(2);

  act(() => callbacks[0]?.(0, {} as VideoFrameCallbackMetadata));
  expect(screen.getByText("等待首帧")).toBeVisible();
  act(() => callbacks[1]?.(0, {} as VideoFrameCallbackMetadata));
  expect(screen.getByText("已有首帧")).toBeVisible();

  rendered.unmount();
});
