import { expect, test, vi } from "vitest";

import { WhepSession } from "@/features/video/mediamtx/whep-session";

function createTrack(id: string, kind: "audio" | "video") {
  const stop = vi.fn();
  const track = {
    id,
    kind,
    stop,
  } as unknown as MediaStreamTrack;
  return { track, stop };
}

function createStream() {
  const tracks: MediaStreamTrack[] = [];
  return {
    addTrack: (track: MediaStreamTrack) => tracks.push(track),
    getTracks: () => [...tracks],
    getAudioTracks: () => tracks.filter((track) => track.kind === "audio"),
    getVideoTracks: () => tracks.filter((track) => track.kind === "video"),
  } as unknown as MediaStream;
}

function createReaderHarness() {
  const configurations: MediaMTXWebRTCReaderConfiguration[] = [];
  const closeSpies: ReturnType<typeof vi.fn>[] = [];
  const readerFactory = (
    configuration: MediaMTXWebRTCReaderConfiguration,
  ): MediaMTXWebRTCReaderInstance => {
    configurations.push(configuration);
    const close = vi.fn();
    closeSpies.push(close);
    return { close };
  };
  return { configurations, closeSpies, readerFactory };
}

test("reader 工厂在 connect 前不加载，异步加载完成后才创建连接", async () => {
  const harness = createReaderHarness();
  const readerFactoryLoader = vi.fn(() =>
    Promise.resolve(harness.readerFactory),
  );
  const session = new WhepSession("https://media.example.invalid/live/whep", {
    readerFactoryLoader,
    mediaStreamFactory: createStream,
  });

  expect(readerFactoryLoader).not.toHaveBeenCalled();
  expect(harness.configurations).toHaveLength(0);

  session.connect();

  expect(session.getSnapshot().status).toBe("connecting");
  expect(readerFactoryLoader).toHaveBeenCalledOnce();
  expect(harness.configurations).toHaveLength(0);
  await vi.waitFor(() => expect(harness.configurations).toHaveLength(1));
  expect(harness.configurations[0]).toMatchObject({
    url: "https://media.example.invalid/live/whep",
    onError: expect.any(Function),
    onTrack: expect.any(Function),
  });
});

test("组装音视频 Track，并把官方重试和最终失败转换成脱敏状态", () => {
  const harness = createReaderHarness();
  const streams: MediaStream[] = [];
  const session = new WhepSession(
    "https://media.example.invalid/live/whep?token=secret-token",
    {
      readerFactory: harness.readerFactory,
      mediaStreamFactory: () => {
        const stream = createStream();
        streams.push(stream);
        return stream;
      },
    },
  );

  session.connect();
  expect(session.getSnapshot().status).toBe("connecting");
  expect(harness.configurations).toHaveLength(1);

  const audioTrack = createTrack("audio-1", "audio");
  const videoTrack = createTrack("video-1", "video");
  harness.configurations[0]?.onTrack?.({
    track: audioTrack.track,
  } as RTCTrackEvent);
  expect(session.getSnapshot()).toMatchObject({
    status: "connecting",
    stream: streams[0],
  });
  harness.configurations[0]?.onTrack?.({
    track: videoTrack.track,
  } as RTCTrackEvent);

  expect(session.getSnapshot()).toMatchObject({
    status: "playing",
    stream: streams[0],
  });
  expect(streams[0]?.getTracks()).toEqual([audioTrack.track, videoTrack.track]);

  harness.configurations[0]?.onError?.(
    "peer connection closed, retrying in some seconds",
  );
  expect(session.getSnapshot()).toMatchObject({
    status: "reconnecting",
    stream: null,
  });
  expect(videoTrack.stop).toHaveBeenCalledOnce();
  expect(audioTrack.stop).toHaveBeenCalledOnce();

  harness.configurations[0]?.onError?.(
    "remote response included secret-token but no retry",
  );
  expect(session.getSnapshot().status).toBe("failed");
  expect(JSON.stringify(session.getSnapshot())).not.toContain("secret-token");
});

test("主动重连关闭旧 reader、忽略迟到回调，close 保持幂等", () => {
  const harness = createReaderHarness();
  const session = new WhepSession("https://media.example.invalid/live/whep", {
    readerFactory: harness.readerFactory,
    mediaStreamFactory: createStream,
  });
  session.connect();
  const oldConfiguration = harness.configurations[0];

  session.reconnect();
  expect(harness.closeSpies[0]).toHaveBeenCalledOnce();
  expect(harness.configurations).toHaveLength(2);
  oldConfiguration?.onTrack?.({
    track: createTrack("late-video", "video").track,
  } as RTCTrackEvent);
  expect(session.getSnapshot().status).toBe("connecting");

  harness.configurations[1]?.onTrack?.({
    track: createTrack("new-video", "video").track,
  } as RTCTrackEvent);
  expect(session.getSnapshot().status).toBe("playing");

  session.close();
  session.close();
  expect(harness.closeSpies[1]).toHaveBeenCalledOnce();
  expect(session.getSnapshot()).toEqual({
    status: "closed",
    stream: null,
  });
});
