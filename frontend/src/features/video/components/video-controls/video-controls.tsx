import { type PropsWithChildren, useState } from "react";

import {
  FullscreenButton,
  PageFullscreenButton,
  PlaybackButton,
  RefreshButton,
} from "@/features/video/components/video-controls/control-buttons";
import {
  VideoControlsBar,
  VideoControlsGroup,
  VideoControlsRoot,
} from "@/features/video/components/video-controls/controls-visibility";
import {
  PlaybackFeedback,
  type PlaybackFeedbackRecoveryAction,
} from "@/features/video/components/video-controls/playback-feedback";
import { VideoDisplayStatusBadge } from "@/features/video/components/video-display-status-badge";
import { useVideoSurface } from "@/features/video/components/video-surface";
import {
  DisabledVolumeControl,
  VolumeControl,
} from "@/features/video/components/video-controls/volume-control";
import type { StreamSessionStatus } from "@/features/video/stream-session/stream-session";
import { useVideoDisplayState } from "@/features/video/display-state";

export type VideoControlsMode = "interactive" | "read-only" | "stopped";

interface VideoControlsProps extends PropsWithChildren {
  status: StreamSessionStatus;
  onReconnect: () => void;
  /** 明确区分可操作、只读和停止状态，避免两个布尔参数产生无效组合。 */
  mode: VideoControlsMode;
}

/**
 * 通用实时视频操作栏入口。children 保留给播放源和显示模式等业务控件组合，通用模块不通过
 * Camera、Source 或 Detail props 控制这些内容。
 */
export function VideoControls({
  status,
  onReconnect,
  mode,
  children,
}: VideoControlsProps) {
  const [controlError, setControlError] = useState<string | null>(null);
  const { actions } = useVideoSurface();
  const displayState = useVideoDisplayState({
    previewActive: mode !== "stopped",
    sessionStatus: status,
  });
  const mediaControlsDisabled = mode !== "interactive";

  let recoveryAction: PlaybackFeedbackRecoveryAction | null = null;
  if (mode === "interactive" && displayState.error?.recovery === "play") {
    recoveryAction = { kind: "play", run: () => void actions.play() };
  } else if (
    mode === "interactive" &&
    displayState.error?.recovery === "reconnect"
  ) {
    recoveryAction = { kind: "reconnect", run: onReconnect };
  }

  return (
    <VideoControlsRoot>
      <PlaybackFeedback
        displayState={displayState}
        recoveryAction={recoveryAction}
        controlError={controlError}
      />
      <VideoControlsBar>
        <VideoControlsGroup>
          <PlaybackButton disabled={mediaControlsDisabled} />
          <RefreshButton
            onReconnect={onReconnect}
            disabled={mediaControlsDisabled}
          />
          {mediaControlsDisabled ? (
            <DisabledVolumeControl />
          ) : (
            <VolumeControl />
          )}
          <VideoDisplayStatusBadge
            sessionStatus={status}
            displayState={displayState}
          />
        </VideoControlsGroup>
        <VideoControlsGroup>
          {children}
          <PageFullscreenButton
            onSuccess={() => setControlError(null)}
            onError={() => setControlError("无法切换网页全屏，请重试。")}
          />
          <FullscreenButton
            onSuccess={() => setControlError(null)}
            onError={() => setControlError("无法切换浏览器全屏，请重试。")}
          />
        </VideoControlsGroup>
      </VideoControlsBar>
    </VideoControlsRoot>
  );
}
