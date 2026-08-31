import {
  type PointerEvent as ReactPointerEvent,
  type PropsWithChildren,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { VideoControlsVisibilityContext } from "@/features/video/components/video-controls/controls-visibility-context";
import { useVideoControlsVisibility } from "@/features/video/components/video-controls/controls-visibility-context";
import { cn } from "@/lib/utils";

const AUTO_HIDE_DELAY_MS = 2_500;

/**
 * 接收整个播放器区域的指针活动并统一管理操作栏显隐。浮层打开时暂停自动隐藏，避免指针从音量
 * 按钮移向 portal 中的 Slider 时，底部操作栏先消失。
 */
export function VideoControlsRoot({ children }: PropsWithChildren) {
  const [visible, setVisible] = useState(false);
  const floatingLayerIdsRef = useRef(new Set<string>());
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearHideTimer = useCallback(() => {
    if (hideTimerRef.current !== null) {
      clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
  }, []);

  const showTemporarily = useCallback(() => {
    setVisible(true);
    clearHideTimer();
    if (floatingLayerIdsRef.current.size === 0) {
      hideTimerRef.current = setTimeout(
        () => setVisible(false),
        AUTO_HIDE_DELAY_MS,
      );
    }
  }, [clearHideTimer]);

  useEffect(() => clearHideTimer, [clearHideTimer]);

  const setFloatingLayerOpen = useCallback(
    (layerId: string, open: boolean) => {
      if (open) {
        floatingLayerIdsRef.current.add(layerId);
      } else {
        floatingLayerIdsRef.current.delete(layerId);
      }
      clearHideTimer();
      if (floatingLayerIdsRef.current.size > 0) {
        setVisible(true);
      } else {
        showTemporarily();
      }
    },
    [clearHideTimer, showTemporarily],
  );

  const handlePointerActivity = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.pointerType !== "touch") {
      showTemporarily();
    }
  };
  const handlePointerLeave = () => {
    if (floatingLayerIdsRef.current.size === 0) {
      clearHideTimer();
      setVisible(false);
    }
  };
  const handlePointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    // 触摸只在点到空白视频区域时切换，点击按钮不得同时把操作栏隐藏。
    if (event.pointerType === "touch" && event.target === event.currentTarget) {
      clearHideTimer();
      setVisible((current) => !current);
    }
  };

  return (
    <VideoControlsVisibilityContext
      value={{
        state: { visible },
        actions: { setFloatingLayerOpen },
      }}
    >
      <div
        role="group"
        aria-label="视频播放器控制层"
        className="pointer-events-auto absolute inset-0 @container"
        onPointerEnter={handlePointerActivity}
        onPointerMove={handlePointerActivity}
        onPointerLeave={handlePointerLeave}
        onPointerUp={handlePointerUp}
      >
        {children}
      </div>
    </VideoControlsVisibilityContext>
  );
}

export function VideoControlsBar({
  className,
  children,
}: PropsWithChildren<{ className?: string }>) {
  const {
    state: { visible },
  } = useVideoControlsVisibility();

  return (
    <div
      role="toolbar"
      aria-label="视频操作"
      className={cn(
        "absolute inset-x-0 bottom-0 flex min-h-16 items-end justify-between gap-3 bg-linear-to-t from-overlay-control-surface/90 via-overlay-control-surface/55 to-transparent px-3 pb-2 pt-7 transition-opacity duration-200 motion-reduce:transition-none sm:px-4 sm:pb-3",
        visible
          ? "pointer-events-auto opacity-100"
          : "pointer-events-none opacity-0",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function VideoControlsGroup({
  className,
  children,
}: PropsWithChildren<{ className?: string }>) {
  return (
    <div className={cn("flex items-center gap-1", className)}>{children}</div>
  );
}
