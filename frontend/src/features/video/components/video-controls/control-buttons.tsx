import {
  ArrowShrinkIcon,
  ChangeScreenModeIcon,
  FullScreenIcon,
  PauseIcon,
  PlayIcon,
  RefreshIcon,
} from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import type { PropsWithChildren } from "react";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useVideoSurface } from "@/features/video/components/video-surface";

function ControlTooltip({
  label,
  children,
}: PropsWithChildren<{ label: string }>) {
  return (
    <Tooltip>
      {children}
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

export function PlaybackButton({ disabled = false }: { disabled?: boolean }) {
  const { state, actions } = useVideoSurface();
  const label = state.paused ? "播放" : "暂停";

  return (
    <ControlTooltip label={label}>
      <TooltipTrigger
        render={
          <Button
            type="button"
            variant="overlay"
            size="icon-sm"
            aria-label={label}
            aria-pressed={!state.paused}
            disabled={disabled}
            onClick={() => void actions.togglePlayback()}
          />
        }
      >
        <HugeiconsIcon
          icon={state.paused ? PlayIcon : PauseIcon}
          strokeWidth={2}
          data-icon="inline-start"
        />
      </TooltipTrigger>
    </ControlTooltip>
  );
}

export function RefreshButton({
  onReconnect,
  disabled = false,
}: {
  onReconnect: () => void;
  disabled?: boolean;
}) {
  const label = "刷新当前流";
  return (
    <ControlTooltip label={label}>
      <TooltipTrigger
        render={
          <Button
            type="button"
            variant="overlay"
            size="icon-sm"
            aria-label={label}
            disabled={disabled}
            onClick={onReconnect}
          />
        }
      >
        <HugeiconsIcon
          icon={RefreshIcon}
          strokeWidth={2}
          data-icon="inline-start"
        />
      </TooltipTrigger>
    </ControlTooltip>
  );
}

export function FullscreenButton({
  onError,
  onSuccess,
}: {
  onError: () => void;
  onSuccess: () => void;
}) {
  const { state, actions } = useVideoSurface();
  if (!state.canFullscreen) {
    return null;
  }

  const label = state.isFullscreen ? "退出浏览器全屏" : "进入浏览器全屏";
  const toggleFullscreen = async () => {
    try {
      await actions.toggleFullscreen();
      // Fullscreen API 的拒绝可能只是一次性的；后续成功后必须撤掉之前的错误提示。
      onSuccess();
    } catch {
      onError();
    }
  };

  return (
    <ControlTooltip label={label}>
      <TooltipTrigger
        render={
          <Button
            type="button"
            variant="overlay"
            size="icon-sm"
            aria-label={label}
            aria-pressed={state.isFullscreen}
            onClick={() => void toggleFullscreen()}
          />
        }
      >
        <HugeiconsIcon
          icon={state.isFullscreen ? ArrowShrinkIcon : FullScreenIcon}
          strokeWidth={2}
          data-icon="inline-start"
        />
      </TooltipTrigger>
    </ControlTooltip>
  );
}

export function PageFullscreenButton({
  onError,
  onSuccess,
}: {
  onError: () => void;
  onSuccess: () => void;
}) {
  const { state, actions } = useVideoSurface();
  const label = state.isPageFullscreen ? "退出网页全屏" : "进入网页全屏";
  const togglePageFullscreen = async () => {
    try {
      await actions.togglePageFullscreen();
      onSuccess();
    } catch {
      onError();
    }
  };

  return (
    <ControlTooltip label={label}>
      <TooltipTrigger
        render={
          <Button
            type="button"
            variant="overlay"
            size="icon-sm"
            aria-label={label}
            aria-pressed={state.isPageFullscreen}
            onClick={() => void togglePageFullscreen()}
          />
        }
      >
        <HugeiconsIcon
          icon={ChangeScreenModeIcon}
          strokeWidth={2}
          data-icon="inline-start"
        />
      </TooltipTrigger>
    </ControlTooltip>
  );
}
