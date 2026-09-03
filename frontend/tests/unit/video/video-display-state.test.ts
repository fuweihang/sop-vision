import { describe, expect, test } from "vitest";

import { deriveVideoDisplayState } from "@/features/video/display-state";
import type { StreamSessionStatus } from "@/features/video/stream-session/stream-session";

const BASE_INPUT = {
  previewActive: true,
  sessionStatus: "playing" as StreamSessionStatus,
  hasPresentedFrame: false,
  frameWaitActive: true,
  playbackError: null,
  presentationError: null,
};

const CASES = [
  {
    name: "预览已停止",
    input: {
      previewActive: false,
      playbackError: "停止后不应展示旧播放错误",
    },
    expected: {
      status: "disabled",
      label: "已停止",
      loading: null,
      error: null,
    },
  },
  {
    name: "等待连接",
    input: { sessionStatus: "idle" },
    expected: {
      status: "idle",
      label: "等待连接",
      loading: { message: "正在加载视频" },
      error: null,
    },
  },
  {
    name: "正在连接",
    input: { sessionStatus: "connecting" },
    expected: {
      status: "connecting",
      label: "正在连接",
      loading: { message: "正在加载视频" },
      error: null,
    },
  },
  {
    name: "正在重连",
    input: {
      sessionStatus: "reconnecting",
      presentationError: "旧画面超时",
    },
    expected: {
      status: "reconnecting",
      label: "正在重连",
      loading: { message: "正在重新连接视频" },
      error: null,
    },
  },
  {
    name: "等待首帧",
    input: {},
    expected: {
      status: "waiting-frame",
      label: "正在加载",
      loading: { message: "正在加载视频" },
      error: null,
    },
  },
  {
    name: "首帧前暂停",
    input: { frameWaitActive: false },
    expected: {
      status: "waiting-frame",
      label: "等待画面",
      loading: null,
      error: null,
    },
  },
  {
    name: "已经出画",
    input: { hasPresentedFrame: true },
    expected: {
      status: "live",
      label: "LIVE",
      loading: null,
      error: null,
    },
  },
  {
    name: "自动播放受阻",
    input: { playbackError: "浏览器拒绝播放" },
    expected: {
      status: "playback-blocked",
      label: "播放受阻",
      loading: null,
      error: {
        kind: "playback",
        message: "浏览器拒绝播放",
        recovery: "play",
      },
    },
  },
  {
    name: "首帧超时",
    input: { presentationError: "等待首帧超时" },
    expected: {
      status: "presentation-failed",
      label: "画面超时",
      loading: null,
      error: {
        kind: "presentation",
        message: "等待首帧超时",
        recovery: "reconnect",
      },
    },
  },
  {
    name: "连接失败",
    input: { sessionStatus: "failed" },
    expected: {
      status: "failed",
      label: "连接失败",
      loading: null,
      error: {
        kind: "session",
        message: "视频连接失败，请刷新当前流。",
        recovery: "reconnect",
      },
    },
  },
  {
    name: "连接关闭",
    input: { sessionStatus: "closed" },
    expected: {
      status: "closed",
      label: "已关闭",
      loading: null,
      error: null,
    },
  },
] satisfies ReadonlyArray<{
  name: string;
  input: Partial<Parameters<typeof deriveVideoDisplayState>[0]>;
  expected: ReturnType<typeof deriveVideoDisplayState>;
}>;

describe("deriveVideoDisplayState", () => {
  test.each(CASES)("$name", ({ input, expected }) => {
    const result = deriveVideoDisplayState({ ...BASE_INPUT, ...input });

    expect(result).toEqual(expected);
  });
});
