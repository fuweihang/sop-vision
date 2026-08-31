import { type PropsWithChildren, useState } from "react";

import { Badge } from "@/components/ui/badge";
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
import { PlaybackFeedback } from "@/features/video/components/video-controls/playback-feedback";
import {
  DisabledVolumeControl,
  VolumeControl,
} from "@/features/video/components/video-controls/volume-control";
import type { StreamSessionStatus } from "@/features/video/stream-session/stream-session";

const STATUS_LABELS = {
  idle: "等待连接",
  connecting: "正在连接",
  playing: "LIVE",
  reconnecting: "正在重连",
  failed: "连接失败",
  closed: "已关闭",
} as const satisfies Record<StreamSessionStatus, string>;

interface VideoControlsProps extends PropsWithChildren {
  status: StreamSessionStatus;
  onReconnect: () => void;
  mediaControlsDisabled?: boolean;
}

/**
 * 通用实时视频操作栏入口。children 保留给播放源和显示模式等业务控件组合，通用模块不通过
 * Camera、Source 或 Detail props 控制这些内容。
 */
export function VideoControls({
  status,
  onReconnect,
  mediaControlsDisabled = false,
  children,
}: VideoControlsProps) {
  const [controlError, setControlError] = useState<string | null>(null);

  return (
    <VideoControlsRoot>
      <PlaybackFeedback
        status={status}
        onReconnect={onReconnect}
        controlError={controlError}
        mediaControlsDisabled={mediaControlsDisabled}
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
          <Badge variant="overlay">{STATUS_LABELS[status]}</Badge>
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
