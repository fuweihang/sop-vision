import { PlayIcon, RefreshIcon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { useVideoSurface } from "@/features/video/components/video-surface";
import type { StreamSessionStatus } from "@/features/video/stream-session/stream-session";

function getLoadingMessage(
  status: StreamSessionStatus,
  hasPresentedFrame: boolean,
  paused: boolean,
) {
  if (status === "reconnecting") {
    return "正在重新连接视频";
  }
  if (status === "idle" || status === "connecting") {
    return "正在加载视频";
  }
  if (status === "playing" && !hasPresentedFrame && !paused) {
    return "正在加载视频";
  }
  return null;
}

interface PlaybackFeedbackProps {
  status: StreamSessionStatus;
  onReconnect: () => void;
  controlError: string | null;
  mediaControlsDisabled: boolean;
}

/** 加载、媒体错误和操作错误不随底部操作栏隐藏，避免用户错过恢复入口。 */
export function PlaybackFeedback({
  status,
  onReconnect,
  controlError,
  mediaControlsDisabled,
}: PlaybackFeedbackProps) {
  const { state, actions } = useVideoSurface();
  const loadingMessage =
    !mediaControlsDisabled && state.presentationError === null
      ? getLoadingMessage(status, state.hasPresentedFrame, state.paused)
      : null;
  const mediaError = mediaControlsDisabled
    ? null
    : (state.playbackError ??
      state.presentationError ??
      (status === "failed" ? "视频连接失败，请刷新当前流。" : null));
  const hasError = mediaError !== null || controlError !== null;

  return (
    <>
      {loadingMessage !== null && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center p-6">
          <div className="flex items-center gap-2 rounded-lg bg-overlay-control-surface/70 px-3 py-2 text-sm text-overlay-control-foreground shadow-sm backdrop-blur-sm">
            <Spinner className="size-5" />
            <span>{loadingMessage}</span>
          </div>
        </div>
      )}
      {hasError && (
        <Alert
          variant="destructive"
          className="pointer-events-auto absolute inset-x-3 bottom-20 z-10 w-auto sm:inset-x-4"
        >
          <AlertDescription className="flex min-w-0 flex-col items-stretch gap-3 @md:flex-row @md:items-center @md:justify-between">
            <span className="min-w-0 flex-1 wrap-anywhere">
              {mediaError ?? controlError}
            </span>
            {!mediaControlsDisabled && state.playbackError !== null && (
              <Button
                type="button"
                size="sm"
                className="self-start @md:self-auto"
                onClick={() => void actions.play()}
              >
                <HugeiconsIcon
                  icon={PlayIcon}
                  strokeWidth={2}
                  data-icon="inline-start"
                />
                继续播放
              </Button>
            )}
            {!mediaControlsDisabled &&
              state.presentationError !== null &&
              state.playbackError === null && (
                <Button type="button" size="sm" onClick={onReconnect}>
                  <HugeiconsIcon
                    icon={RefreshIcon}
                    strokeWidth={2}
                    data-icon="inline-start"
                  />
                  刷新当前流
                </Button>
              )}
          </AlertDescription>
        </Alert>
      )}
    </>
  );
}
