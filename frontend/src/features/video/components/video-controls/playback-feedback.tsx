import { PlayIcon, RefreshIcon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import type { VideoDisplayState } from "@/features/video/display-state";

export type PlaybackFeedbackRecoveryAction =
  { kind: "play"; run: () => void } | { kind: "reconnect"; run: () => void };

interface PlaybackFeedbackProps {
  displayState: VideoDisplayState;
  recoveryAction: PlaybackFeedbackRecoveryAction | null;
  controlError: string | null;
}

/** 加载、媒体错误和操作错误不随底部操作栏隐藏，避免用户错过恢复入口。 */
export function PlaybackFeedback({
  displayState,
  recoveryAction,
  controlError,
}: PlaybackFeedbackProps) {
  // 父组件已经根据操作栏模式决定动作是否可用；这里不读取 VideoSurface，也不重新判断权限。
  const loadingMessage = displayState.loading?.message ?? null;
  const mediaError = displayState.error?.message ?? null;
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
            {recoveryAction?.kind === "play" && (
              <Button
                type="button"
                size="sm"
                className="self-start @md:self-auto"
                onClick={recoveryAction.run}
              >
                <HugeiconsIcon
                  icon={PlayIcon}
                  strokeWidth={2}
                  data-icon="inline-start"
                />
                继续播放
              </Button>
            )}
            {recoveryAction?.kind === "reconnect" && (
              <Button type="button" size="sm" onClick={recoveryAction.run}>
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
