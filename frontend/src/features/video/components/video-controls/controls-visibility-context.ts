import { createContext, use } from "react";

interface VideoControlsVisibilityContextValue {
  state: { visible: boolean };
  actions: {
    setFloatingLayerOpen: (layerId: string, open: boolean) => void;
  };
}

export const VideoControlsVisibilityContext =
  createContext<VideoControlsVisibilityContextValue | null>(null);

/** 供操作栏内的浮层扩展登记开关状态，避免浮层打开时操作栏自动隐藏。 */
export function useVideoControlsVisibility() {
  const context = use(VideoControlsVisibilityContext);
  if (context === null) {
    throw new Error("播放器操作栏扩展必须放在 VideoControls 内使用。");
  }
  return context;
}
