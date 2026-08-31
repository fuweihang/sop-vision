import { createContext, use } from "react";

import type {
  RenderedMediaRect,
  VideoSize,
} from "@/features/video/geometry/video-geometry";

export interface VideoSurfaceContextValue {
  state: {
    sourceSize: VideoSize;
    containerSize: VideoSize;
    renderedMediaRect: RenderedMediaRect;
    hasAudio: boolean;
    hasPresentedFrame: boolean;
    paused: boolean;
    muted: boolean;
    volume: number;
    canFullscreen: boolean;
    isFullscreen: boolean;
    isPageFullscreen: boolean;
    playbackError: string | null;
    presentationError: string | null;
  };
  actions: {
    play: () => Promise<void>;
    pause: () => void;
    togglePlayback: () => Promise<void>;
    setMuted: (muted: boolean) => void;
    setVolume: (volume: number) => void;
    requestFullscreen: () => Promise<void>;
    exitFullscreen: () => Promise<void>;
    toggleFullscreen: () => Promise<void>;
    requestPageFullscreen: () => Promise<void>;
    exitPageFullscreen: () => void;
    togglePageFullscreen: () => Promise<void>;
  };
  meta: {
    videoElement: HTMLVideoElement | null;
    containerElement: HTMLDivElement | null;
  };
}

export const VideoSurfaceContext =
  createContext<VideoSurfaceContextValue | null>(null);

/** VideoSurface 的 children 通过该入口读取媒体测量值，不能依赖组件内部 DOM 结构。 */
export function useVideoSurface() {
  const context = use(VideoSurfaceContext);
  if (context === null) {
    throw new Error("useVideoSurface 必须在 VideoSurface 内使用。");
  }
  return context;
}
