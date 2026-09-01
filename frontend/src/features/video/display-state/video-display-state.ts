import type { StreamSessionStatus } from "@/features/video/stream-session/stream-session";

interface VideoDisplayStateBase {
  label: string;
}

interface VideoDisplayLoading {
  message: string;
}

type VideoDisplayErrorKind = "playback" | "presentation" | "session";
export type VideoDisplayRecovery = "play" | "reconnect";

interface VideoDisplayError<
  Kind extends VideoDisplayErrorKind,
  Recovery extends VideoDisplayRecovery,
> {
  kind: Kind;
  message: string;
  recovery: Recovery;
}

/**
 * `status` 是判别字段，类型会阻止 LIVE/关闭状态携带 loading，也会阻止错误状态缺少对应恢复方式。
 * `waiting-frame` 允许没有 loading：用户首帧前主动暂停时仍未出画，但浏览器没有继续等待新帧。
 */
export type VideoDisplayState =
  | (VideoDisplayStateBase & {
      status: "disabled" | "closed" | "live";
      loading: null;
      error: null;
    })
  | (VideoDisplayStateBase & {
      status: "idle" | "connecting" | "reconnecting";
      loading: VideoDisplayLoading;
      error: null;
    })
  | (VideoDisplayStateBase & {
      status: "waiting-frame";
      loading: VideoDisplayLoading | null;
      error: null;
    })
  | (VideoDisplayStateBase & {
      status: "playback-blocked";
      loading: null;
      error: VideoDisplayError<"playback", "play">;
    })
  | (VideoDisplayStateBase & {
      status: "presentation-failed";
      loading: null;
      error: VideoDisplayError<"presentation", "reconnect">;
    })
  | (VideoDisplayStateBase & {
      status: "failed";
      loading: null;
      error: VideoDisplayError<"session", "reconnect">;
    });

export interface DeriveVideoDisplayStateInput {
  previewActive: boolean;
  sessionStatus: StreamSessionStatus;
  hasPresentedFrame: boolean;
  frameWaitActive: boolean;
  playbackError: string | null;
  presentationError: string | null;
}

/**
 * 把共享 Session 状态和当前 video DOM 的播放结果组合成用户可见状态。
 *
 * `playing` 只表示 Session 已收到视频 Track；同一 MediaStream 的不同 video 可能尚未同时出画，因此
 * `waiting-frame/live` 必须在每个 VideoSurface 内分别计算，不能写回共享 Session。播放/暂停仍由
 * VideoSurface 的播放按钮表达；这里只接收 `frameWaitActive`，防止暂停期间显示不会结束的 loading。
 */
export function deriveVideoDisplayState({
  previewActive,
  sessionStatus,
  hasPresentedFrame,
  frameWaitActive,
  playbackError,
  presentationError,
}: DeriveVideoDisplayStateInput): VideoDisplayState {
  if (!previewActive) {
    return {
      status: "disabled",
      label: "已停止",
      loading: null,
      error: null,
    };
  }

  if (sessionStatus === "idle") {
    return {
      status: "idle",
      label: "等待连接",
      loading: { message: "正在加载视频" },
      error: null,
    };
  }
  if (sessionStatus === "connecting") {
    return {
      status: "connecting",
      label: "正在连接",
      loading: { message: "正在加载视频" },
      error: null,
    };
  }
  if (sessionStatus === "reconnecting") {
    // 重连优先于旧 Stream 留下的首帧超时，避免用户点击刷新后仍看到过期错误而看不到重连进度。
    return {
      status: "reconnecting",
      label: "正在重连",
      loading: { message: "正在重新连接视频" },
      error: null,
    };
  }
  if (sessionStatus === "failed") {
    return {
      status: "failed",
      label: "连接失败",
      loading: null,
      error: {
        kind: "session",
        message: "视频连接失败，请刷新当前流。",
        recovery: "reconnect",
      },
    };
  }
  if (sessionStatus === "closed") {
    return {
      status: "closed",
      label: "已关闭",
      loading: null,
      error: null,
    };
  }

  // 以下分支只处理 playing。播放和画面错误属于当前 video，优先于“等待首帧”和 LIVE。
  if (playbackError !== null) {
    return {
      status: "playback-blocked",
      label: "播放受阻",
      loading: null,
      error: {
        kind: "playback",
        message: playbackError,
        recovery: "play",
      },
    };
  }
  if (presentationError !== null) {
    return {
      status: "presentation-failed",
      label: "画面超时",
      loading: null,
      error: {
        kind: "presentation",
        message: presentationError,
        recovery: "reconnect",
      },
    };
  }
  if (!hasPresentedFrame) {
    return {
      status: "waiting-frame",
      label: frameWaitActive ? "正在加载" : "等待画面",
      loading: frameWaitActive ? { message: "正在加载视频" } : null,
      error: null,
    };
  }
  return {
    status: "live",
    label: "LIVE",
    loading: null,
    error: null,
  };
}
