import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { CameraDetailPlayer } from "@/features/cameras/components/camera-detail-player";
import { renderWithStreamSession } from "@/features/cameras/testing/render-with-stream-session";
import { buildCameraDetail } from "@/mocks/cameras/fixtures";
import { setDocumentVisibility } from "@/test/browser-mocks";
import { installPlayingMediaElementMocks } from "@/test/media-browser-mocks";

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

function getDefaultSource() {
  const source = buildCameraDetail().sources[0];
  if (source === undefined) {
    throw new Error("Camera Fixture 缺少默认 Source。");
  }
  return source;
}

function player(
  source: ReturnType<typeof getDefaultSource> | null,
  previewRequested: boolean,
) {
  return (
    <CameraDetailPlayer
      sources={source === null ? buildCameraDetail().sources : [source]}
      source={source}
      previewRequested={previewRequested}
      onSourceChange={vi.fn()}
    />
  );
}

test("按预览意图 acquire/release，页面隐藏时保持 Lease", async () => {
  const source = getDefaultSource();
  const result = renderWithStreamSession(player(source, true));
  const video = screen.getByLabelText("实时视频");
  expect(video).toHaveAttribute("autoplay");
  expect(video).toHaveAttribute("playsinline");
  expect(video).not.toHaveAttribute("controls");
  await waitFor(() => expect(result.fakeStreamSessions).toHaveLength(1));
  expect(result.streamSessionManager.activeSessionCount).toBe(1);

  act(() => setDocumentVisibility("hidden"));
  expect(result.streamSessionManager.activeSessionCount).toBe(1);
  expect(result.fakeStreamSessions).toHaveLength(1);

  result.rerender(player(source, false));
  expect(screen.getByText("预览已停止")).toBeVisible();
  expect(screen.getByText("已停止")).toBeVisible();
  expect(screen.getByRole("toolbar", { name: "视频操作" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /^(播放|暂停)$/ })).toBeDisabled();
  expect(screen.getByRole("button", { name: "刷新当前流" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "取消静音" })).toBeDisabled();
  expect(screen.getByRole("combobox", { name: "切换预览源" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "进入网页全屏" })).toBeEnabled();
  expect(screen.queryByText("正在加载视频")).not.toBeInTheDocument();
  await act(() => Promise.resolve());
  expect(result.streamSessionManager.activeSessionCount).toBe(0);
  expect(result.fakeStreamSessions[0]?.closeCount).toBe(1);

  result.rerender(player(source, true));
  await waitFor(() => expect(result.fakeStreamSessions).toHaveLength(2));
  expect(result.streamSessionManager.activeSessionCount).toBe(1);

  result.unmount();
  await act(() => Promise.resolve());
  expect(result.streamSessionManager.activeSessionCount).toBe(0);
  expect(result.fakeStreamSessions[1]?.closeCount).toBe(1);
});

test("暂停只影响当前 video，刷新继续保留暂停或播放意图", async () => {
  const user = userEvent.setup();
  const media = installPlayingMediaElementMocks();
  const result = renderWithStreamSession(player(getDefaultSource(), true));
  await waitFor(() => expect(result.fakeStreamSessions).toHaveLength(1));
  const session = result.fakeStreamSessions[0];

  act(() => {
    session?.emit({
      status: "playing",
      stream: createPlaybackStream(),
    });
  });
  await user.click(await screen.findByRole("button", { name: "暂停" }));
  expect(media.pause).toHaveBeenCalledOnce();
  expect(result.streamSessionManager.activeSessionCount).toBe(1);
  expect(session?.closeCount).toBe(0);

  await user.click(screen.getByRole("button", { name: "刷新当前流" }));
  expect(session?.reconnectCount).toBe(1);
  expect(screen.getByRole("button", { name: "播放" })).toBeEnabled();
  expect(screen.getByText("正在加载视频")).toBeVisible();
  act(() => {
    session?.emit({
      status: "playing",
      stream: createPlaybackStream(),
    });
  });
  expect(screen.getByRole("button", { name: "播放" })).toBeEnabled();
  expect(media.play).toHaveBeenCalledOnce();
  expect(screen.getByText("等待画面")).toBeVisible();
  expect(screen.queryByText("正在加载视频")).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "播放" }));
  expect(media.play).toHaveBeenCalledTimes(2);
  expect(screen.getByText("正在加载视频")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "刷新当前流" }));
  expect(session?.reconnectCount).toBe(2);
  act(() => {
    session?.emit({
      status: "playing",
      stream: createPlaybackStream(),
    });
  });
  expect(await screen.findByRole("button", { name: "暂停" })).toBeEnabled();
  expect(media.play).toHaveBeenCalledTimes(3);
  expect(result.streamSessionManager.activeSessionCount).toBe(1);
});

test("临时切源会退出旧 Source 的暂停状态并自动播放新 Stream", async () => {
  const user = userEvent.setup();
  const media = installPlayingMediaElementMocks();
  const camera = buildCameraDetail({
    sources: [{ status: "ONLINE" }, { status: "ONLINE" }],
  });
  const firstSource = camera.sources[0];
  const secondSource = camera.sources[1];
  if (firstSource === undefined || secondSource === undefined) {
    throw new Error("测试 Camera 缺少双路 Source。");
  }
  const onSourceChange = vi.fn();
  const result = renderWithStreamSession(
    <CameraDetailPlayer
      sources={camera.sources}
      source={firstSource}
      previewRequested
      onSourceChange={onSourceChange}
    />,
  );
  await waitFor(() => expect(result.fakeStreamSessions).toHaveLength(1));
  act(() => {
    result.fakeStreamSessions[0]?.emit({
      status: "playing",
      stream: createPlaybackStream(),
    });
  });
  await user.click(await screen.findByRole("button", { name: "暂停" }));

  result.rerender(
    <CameraDetailPlayer
      sources={camera.sources}
      source={secondSource}
      previewRequested
      onSourceChange={onSourceChange}
    />,
  );
  await waitFor(() => expect(result.fakeStreamSessions).toHaveLength(2));
  act(() => {
    result.fakeStreamSessions[1]?.emit({
      status: "playing",
      stream: createPlaybackStream(),
    });
  });

  expect(await screen.findByRole("button", { name: "暂停" })).toBeEnabled();
  expect(media.play).toHaveBeenCalledTimes(3);
  expect(result.fakeStreamSessions[0]?.closeCount).toBe(1);
});

test("whep_url 缺失时不 acquire，入口恢复后按现有预览意图开始", async () => {
  const source = getDefaultSource();
  const result = renderWithStreamSession(player(null, true));

  expect(screen.getByText("当前视频源不可播放")).toBeVisible();
  expect(result.fakeStreamSessions).toHaveLength(0);
  expect(screen.queryByRole("toolbar", { name: "视频操作" })).toBeNull();

  result.rerender(player(source, true));
  await waitFor(() => expect(result.fakeStreamSessions).toHaveLength(1));
  expect(result.streamSessionManager.activeSessionCount).toBe(1);
  expect(screen.getByRole("toolbar", { name: "视频操作" })).toBeInTheDocument();
});

test("只有 Source ID 或 WHEP URL 变化才切换详情 Lease", async () => {
  const source = getDefaultSource();
  const result = renderWithStreamSession(player(source, true));
  await waitFor(() => expect(result.fakeStreamSessions).toHaveLength(1));

  const renamedSource = { ...source, name: "刷新后的显示名称" };
  result.rerender(player(renamedSource, true));
  await act(() => Promise.resolve());
  expect(result.fakeStreamSessions).toHaveLength(1);
  expect(result.fakeStreamSessions[0]?.closeCount).toBe(0);

  const changedUrlSource = {
    ...renamedSource,
    whep_url: "https://media.example.invalid/detail-changed/whep",
  };
  result.rerender(player(changedUrlSource, true));
  await waitFor(() => expect(result.fakeStreamSessions).toHaveLength(2));
  expect(result.fakeStreamSessions[0]?.closeCount).toBe(1);

  const changedIdSource = {
    ...changedUrlSource,
    source_id: "91b74192-2d6b-4f24-8d31-7706421f8751",
  };
  result.rerender(player(changedIdSource, true));
  await waitFor(() => expect(result.fakeStreamSessions).toHaveLength(3));
  expect(result.fakeStreamSessions[1]?.closeCount).toBe(1);
  expect(result.streamSessionManager.activeSessionCount).toBe(1);
});
