import { useCallback, useEffect, useState } from "react";

/** 封装 Fullscreen API 和 fullscreenchange，避免上层组件直接依赖 document 状态。 */
export function useVideoFullscreen(containerElement: HTMLDivElement | null) {
  const [isFullscreen, setIsFullscreen] = useState(false);

  const requestFullscreen = useCallback(async () => {
    if (containerElement?.requestFullscreen === undefined) {
      throw new Error("当前浏览器不支持播放器全屏。");
    }
    await containerElement.requestFullscreen();
  }, [containerElement]);

  const exitFullscreen = useCallback(async () => {
    if (document.exitFullscreen === undefined) {
      throw new Error("当前浏览器不支持退出播放器全屏。");
    }
    await document.exitFullscreen();
  }, []);

  const toggleFullscreen = useCallback(async () => {
    if (document.fullscreenElement === containerElement) {
      await exitFullscreen();
    } else {
      await requestFullscreen();
    }
  }, [containerElement, exitFullscreen, requestFullscreen]);

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(document.fullscreenElement === containerElement);
    };
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    handleFullscreenChange();
    return () =>
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, [containerElement]);

  return {
    state: {
      canFullscreen:
        containerElement?.requestFullscreen !== undefined &&
        document.exitFullscreen !== undefined,
      isFullscreen,
    },
    actions: {
      requestFullscreen,
      exitFullscreen,
      toggleFullscreen,
    },
  };
}
