import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import type { CameraDefaultPreviewSource } from "@/features/cameras/api/cameras-api";
import { CameraCardPreview } from "@/features/cameras/components/camera-card-preview";
import { CameraDetailPlayer } from "@/features/cameras/components/camera-detail-player";
import {
  buildCameraDetail,
  buildCameraSummary,
  type CameraSourceFixtureInput,
} from "@/mocks/cameras/fixtures";
import { setDocumentVisibility } from "@/test/browser-mocks";
import { installMediaElementMocks } from "@/test/media-browser-mocks";

import { renderWithStreamSession } from "../../support/cameras/render-with-stream-session";

function buildPreviewSource(
  sourceOverrides: readonly CameraSourceFixtureInput[] = [{ status: "ONLINE" }],
) {
  return buildCameraSummary(buildCameraDetail({ sources: sourceOverrides }))
    .default_preview_source;
}

function createPlaybackStream() {
  const videoTrack = {
    id: "card-video-1",
    kind: "video",
    stop: vi.fn(),
  } as unknown as MediaStreamTrack;
  return {
    getTracks: () => [videoTrack],
    getAudioTracks: () => [],
    getVideoTracks: () => [videoTrack],
  } as unknown as MediaStream;
}

test("WHEP URL 缺失时显示非 video 占位和不可预览状态", () => {
  const source = buildPreviewSource([
    { name: "暂不可用的主码流", status: "OFFLINE", whep_url: null },
  ]);
  const result = renderWithStreamSession(<CameraCardPreview source={source} />);

  expect(screen.queryByLabelText("实时视频")).toBeNull();
  expect(screen.getByText("暂不可用的主码流")).toBeVisible();
  expect(screen.queryByText("离线")).toBeNull();
  expect(screen.getByText("不可预览")).toBeVisible();
  expect(screen.queryByRole("status", { name: "正在加载视频" })).toBeNull();
  expect(result.fakeStreamSessions).toHaveLength(0);
  expect(result.streamSessionManager.activeSessionCount).toBe(0);
});

test("挂载期间持有 Lease，页面 hidden 不释放，并投影浏览器 Session 状态", async () => {
  installMediaElementMocks();
  const source = buildPreviewSource();
  const result = renderWithStreamSession(<CameraCardPreview source={source} />);

  const video = screen.getByLabelText<HTMLVideoElement>("实时视频");
  expect(video).toHaveAttribute("autoplay");
  expect(video).toHaveAttribute("playsinline");
  expect(video).not.toHaveAttribute("controls");
  expect(video.muted).toBe(true);
  expect(video.volume).toBe(0);
  await waitFor(() => expect(result.fakeStreamSessions).toHaveLength(1));
  expect(result.streamSessionManager.activeSessionCount).toBe(1);
  const sessionStatus = screen.getByText("正在连接");
  expect(sessionStatus).toBeVisible();
  expect(screen.queryByText("正在加载视频")).toBeNull();
  expect(screen.getByRole("status", { name: "正在加载视频" })).toBeVisible();

  act(() => setDocumentVisibility("hidden"));
  expect(result.streamSessionManager.activeSessionCount).toBe(1);
  expect(result.fakeStreamSessions[0]?.closeCount).toBe(0);

  act(() => {
    result.fakeStreamSessions[0]?.emit({
      status: "playing",
      stream: createPlaybackStream(),
    });
  });
  expect(screen.getByText("正在加载")).toBeVisible();
  expect(screen.queryByText("LIVE")).toBeNull();
  fireEvent.loadedData(video);
  expect(screen.getByText("LIVE")).toBeVisible();
  expect(screen.queryByRole("status", { name: "正在加载视频" })).toBeNull();

  act(() => {
    result.fakeStreamSessions[0]?.emit({
      status: "reconnecting",
      stream: null,
    });
  });
  expect(screen.getByText("正在重连")).toBeVisible();
  expect(screen.queryByText("正在重新连接视频")).toBeNull();
  expect(
    screen.getByRole("status", { name: "正在重新连接视频" }),
  ).toBeVisible();

  act(() => {
    result.fakeStreamSessions[0]?.emit({ status: "failed", stream: null });
  });
  expect(screen.getByText("连接失败")).toBeVisible();
  expect(screen.queryByRole("status", { name: "正在加载视频" })).toBeNull();
});

test("首帧等待十秒后停止 loading 并显示画面超时", async () => {
  vi.useFakeTimers();
  installMediaElementMocks();
  try {
    const result = renderWithStreamSession(
      <CameraCardPreview source={buildPreviewSource()} />,
    );
    await act(() => Promise.resolve());
    act(() => {
      result.fakeStreamSessions[0]?.emit({
        status: "playing",
        stream: createPlaybackStream(),
      });
    });

    expect(screen.queryByText("正在加载视频")).toBeNull();
    expect(screen.getByRole("status", { name: "正在加载视频" })).toBeVisible();
    await act(() => vi.advanceTimersByTimeAsync(10_000));
    expect(screen.queryByRole("status", { name: "正在加载视频" })).toBeNull();
    expect(screen.getByText("画面超时")).toBeVisible();
  } finally {
    vi.useRealTimers();
  }
});

test("非媒体字段刷新保留 Lease，ID、URL 改变或变空时切换并释放", async () => {
  const initialSource = buildPreviewSource();
  const result = renderWithStreamSession(
    <CameraCardPreview source={initialSource} />,
  );
  await waitFor(() => expect(result.fakeStreamSessions).toHaveLength(1));

  const renamedSource: CameraDefaultPreviewSource = {
    ...initialSource,
    name: "刷新后的主码流名称",
  };
  result.rerender(<CameraCardPreview source={renamedSource} />);
  expect(screen.getByText("刷新后的主码流名称")).toBeVisible();
  expect(result.fakeStreamSessions).toHaveLength(1);
  expect(result.fakeStreamSessions[0]?.closeCount).toBe(0);

  const changedUrlSource: CameraDefaultPreviewSource = {
    ...renamedSource,
    whep_url: "https://media.example.invalid/changed/whep",
  };
  result.rerender(<CameraCardPreview source={changedUrlSource} />);
  await waitFor(() => expect(result.fakeStreamSessions).toHaveLength(2));
  expect(result.fakeStreamSessions[0]?.closeCount).toBe(1);
  expect(result.streamSessionManager.activeSessionCount).toBe(1);

  const changedIdSource: CameraDefaultPreviewSource = {
    ...changedUrlSource,
    source_id: "91b74192-2d6b-4f24-8d31-7706421f8751",
  };
  result.rerender(<CameraCardPreview source={changedIdSource} />);
  await waitFor(() => expect(result.fakeStreamSessions).toHaveLength(3));
  expect(result.fakeStreamSessions[1]?.closeCount).toBe(1);
  expect(result.streamSessionManager.activeSessionCount).toBe(1);

  result.rerender(
    <CameraCardPreview source={{ ...changedIdSource, whep_url: null }} />,
  );
  expect(screen.queryByLabelText("实时视频")).toBeNull();
  await act(() => Promise.resolve());
  expect(result.fakeStreamSessions[2]?.closeCount).toBe(1);
  expect(result.streamSessionManager.activeSessionCount).toBe(0);
});

test("Card 与 Detail 同源时共享 Session，逐个释放后才关闭", async () => {
  installMediaElementMocks();
  const camera = buildCameraDetail({ sources: [{ status: "ONLINE" }] });
  const source = (() => {
    const firstSource = camera.sources[0];
    if (firstSource === undefined) {
      throw new Error("测试 Camera 缺少默认 Source。");
    }
    return firstSource;
  })();
  const summarySource = buildCameraSummary(camera).default_preview_source;

  function SharedConsumers({
    showCard,
    showDetail,
  }: {
    showCard: boolean;
    showDetail: boolean;
  }) {
    return (
      <>
        {showCard ? (
          <CameraCardPreview key="card" source={summarySource} />
        ) : null}
        {showDetail ? (
          <CameraDetailPlayer
            key="detail"
            sources={camera.sources}
            source={source}
            previewRequested
            onSourceChange={vi.fn()}
          />
        ) : null}
      </>
    );
  }

  const result = renderWithStreamSession(
    <SharedConsumers showCard showDetail />,
  );
  await waitFor(() => expect(result.fakeStreamSessions).toHaveLength(1));
  expect(screen.getAllByLabelText("实时视频")).toHaveLength(2);
  expect(result.streamSessionManager.activeSessionCount).toBe(1);

  result.rerender(<SharedConsumers showCard={false} showDetail />);
  await act(() => Promise.resolve());
  expect(result.fakeStreamSessions[0]?.closeCount).toBe(0);
  expect(result.streamSessionManager.activeSessionCount).toBe(1);

  result.rerender(<SharedConsumers showCard={false} showDetail={false} />);
  await act(() => Promise.resolve());
  expect(result.fakeStreamSessions[0]?.closeCount).toBe(1);
  expect(result.streamSessionManager.activeSessionCount).toBe(0);
});

test("多个 Card 共享同一 Session、各自保留 video，并在最后卸载后关闭", async () => {
  installMediaElementMocks();
  const source = buildPreviewSource();
  const result = renderWithStreamSession(
    <>
      <CameraCardPreview source={source} />
      <CameraCardPreview source={source} />
    </>,
  );

  await waitFor(() => expect(result.fakeStreamSessions).toHaveLength(1));
  const videos = screen.getAllByLabelText<HTMLVideoElement>("实时视频");
  expect(videos).toHaveLength(2);
  expect(result.streamSessionManager.activeSessionCount).toBe(1);

  // Session 和 MediaStream 共享，但首帧由各自的 video DOM 独立确认。
  act(() => {
    result.fakeStreamSessions[0]?.emit({
      status: "playing",
      stream: createPlaybackStream(),
    });
  });
  expect(screen.getAllByText("正在加载")).toHaveLength(2);
  if (videos[0] === undefined) {
    throw new Error("第一个 Camera Card 缺少 video。");
  }
  fireEvent.loadedData(videos[0]);
  expect(screen.getAllByText("LIVE")).toHaveLength(1);
  expect(screen.getAllByText("正在加载")).toHaveLength(1);

  result.unmount();
  await act(() => Promise.resolve());
  expect(result.fakeStreamSessions[0]?.closeCount).toBe(1);
  expect(result.streamSessionManager.activeSessionCount).toBe(0);
});

test("Strict Mode 重挂载不重复创建 Session，真实卸载后释放", async () => {
  const result = renderWithStreamSession(
    <CameraCardPreview source={buildPreviewSource()} />,
    { strict: true },
  );

  await act(() => Promise.resolve());
  expect(result.fakeStreamSessions).toHaveLength(1);
  expect(result.streamSessionManager.activeSessionCount).toBe(1);

  result.unmount();
  await act(() => Promise.resolve());
  expect(result.fakeStreamSessions[0]?.closeCount).toBe(1);
  expect(result.streamSessionManager.activeSessionCount).toBe(0);
});
