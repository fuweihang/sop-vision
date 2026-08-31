import { VolumeHighIcon, VolumeOffIcon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { useEffect, useId, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Slider } from "@/components/ui/slider";
import { useVideoControlsVisibility } from "@/features/video/components/video-controls/controls-visibility-context";
import { useVideoSurface } from "@/features/video/components/video-surface";

const POPOVER_CLOSE_DELAY_MS = 150;
const DEFAULT_UNMUTED_VOLUME = 0.7;

export function VolumeControl() {
  const {
    state,
    actions,
    meta: { containerElement },
  } = useVideoSurface();
  const {
    actions: { setFloatingLayerOpen },
  } = useVideoControlsVisibility();
  const [open, setOpen] = useState(false);
  const volumeLabelId = useId();
  const unmuteVolumeRef = useRef(
    state.volume > 0 ? state.volume : DEFAULT_UNMUTED_VOLUME,
  );
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const volumePercent = Math.round(state.volume * 100);

  useEffect(
    () => () => {
      if (closeTimerRef.current !== null) {
        clearTimeout(closeTimerRef.current);
      }
      setFloatingLayerOpen(volumeLabelId, false);
    },
    [setFloatingLayerOpen, volumeLabelId],
  );

  const setPopoverOpen = (nextOpen: boolean) => {
    setOpen(nextOpen);
    setFloatingLayerOpen(volumeLabelId, nextOpen);
  };

  const cancelClose = () => {
    if (closeTimerRef.current !== null) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
    setPopoverOpen(true);
  };
  const scheduleClose = () => {
    if (closeTimerRef.current !== null) {
      clearTimeout(closeTimerRef.current);
    }
    closeTimerRef.current = setTimeout(
      () => setPopoverOpen(false),
      POPOVER_CLOSE_DELAY_MS,
    );
  };
  const toggleMuted = () => {
    if (state.muted) {
      if (state.volume === 0) {
        actions.setVolume(unmuteVolumeRef.current);
      }
      actions.setMuted(false);
      return;
    }

    // 静音按钮同时把受控 Slider 归零，并保存恢复点供下一次点击取消静音使用。
    if (state.volume > 0) {
      unmuteVolumeRef.current = state.volume;
    }
    actions.setVolume(0);
    actions.setMuted(true);
  };
  const handleVolumeChange = (value: number | readonly number[]) => {
    const nextPercent = typeof value === "number" ? value : value[0];
    if (nextPercent === undefined) {
      return;
    }
    const nextVolume = nextPercent / 100;
    if (nextVolume === 0) {
      // Slider 归零不是静音按钮操作，不保留拖动途中经过的 1% 等临时值；下次恢复到 70%。
      unmuteVolumeRef.current = DEFAULT_UNMUTED_VOLUME;
    }
    actions.setVolume(nextVolume);
    actions.setMuted(nextVolume === 0);
  };

  return (
    // Popover 完全由 hover 状态控制，不接收 Trigger 的点击开关请求。
    <Popover open={open}>
      <PopoverTrigger
        render={
          <Button
            type="button"
            variant="overlay"
            size="icon-sm"
            aria-label={state.muted ? "取消静音" : "静音"}
            aria-pressed={state.muted}
          />
        }
        onClick={toggleMuted}
        onMouseEnter={cancelClose}
        onMouseLeave={scheduleClose}
      >
        <HugeiconsIcon
          icon={state.muted ? VolumeOffIcon : VolumeHighIcon}
          strokeWidth={2}
          data-icon="inline-start"
        />
      </PopoverTrigger>
      <PopoverContent
        // 浏览器全屏只渲染全屏元素及其后代。音量浮层必须挂到播放器容器内，不能留在 body Portal。
        portalContainer={containerElement}
        side="top"
        sideOffset={4}
        className="w-fit min-w-0 items-center gap-0 p-1.5"
        onMouseEnter={cancelClose}
        onMouseLeave={scheduleClose}
      >
        <PopoverTitle id={volumeLabelId} className="sr-only">
          音量
        </PopoverTitle>
        <Slider
          aria-labelledby={volumeLabelId}
          data-volume-percent={volumePercent}
          orientation="vertical"
          className="h-20 [&_[data-base-ui-slider-control]]:min-h-20! [&_[data-slot=slider-thumb]]:size-2.5! [&_[data-slot=slider-track]]:w-0.5!"
          min={0}
          max={100}
          step={1}
          value={[volumePercent]}
          onValueChange={handleVolumeChange}
        />
      </PopoverContent>
    </Popover>
  );
}

/** 停止预览后保留音量图标的位置，但不创建可交互 Popover。 */
export function DisabledVolumeControl() {
  const { state } = useVideoSurface();

  return (
    <Button
      type="button"
      variant="overlay"
      size="icon-sm"
      aria-label={state.muted ? "取消静音" : "静音"}
      aria-pressed={state.muted}
      disabled
    >
      <HugeiconsIcon
        icon={state.muted ? VolumeOffIcon : VolumeHighIcon}
        strokeWidth={2}
        data-icon="inline-start"
      />
    </Button>
  );
}
