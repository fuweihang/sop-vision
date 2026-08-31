import { useEffect, useMemo, useState } from "react";

import {
  calculateRenderedMediaRect,
  type VideoObjectFit,
  type VideoSize,
} from "@/features/video/geometry/video-geometry";

const EMPTY_SIZE: VideoSize = { width: 0, height: 0 };

interface UseVideoLayoutOptions {
  videoElement: HTMLVideoElement | null;
  containerElement: HTMLDivElement | null;
  objectFit: VideoObjectFit;
}

/** 监听视频原始尺寸和容器尺寸，并计算 cover/contain 后真正显示视频的区域。 */
export function useVideoLayout({
  videoElement,
  containerElement,
  objectFit,
}: UseVideoLayoutOptions) {
  const [sourceSize, setSourceSize] = useState<VideoSize>(EMPTY_SIZE);
  const [containerSize, setContainerSize] = useState<VideoSize>(EMPTY_SIZE);

  useEffect(() => {
    if (containerElement === null) {
      return;
    }

    const updateContainerSize = () => {
      const rect = containerElement.getBoundingClientRect();
      setContainerSize({ width: rect.width, height: rect.height });
    };
    updateContainerSize();

    if (typeof ResizeObserver === "undefined") {
      // 旧浏览器没有 ResizeObserver 时仍监听窗口变化，至少覆盖常见的响应式布局调整。
      window.addEventListener("resize", updateContainerSize);
      return () => window.removeEventListener("resize", updateContainerSize);
    }

    const observer = new ResizeObserver(updateContainerSize);
    observer.observe(containerElement);
    return () => observer.disconnect();
  }, [containerElement]);

  useEffect(() => {
    if (videoElement === null) {
      return;
    }

    const updateSourceSize = () => {
      setSourceSize({
        width: videoElement.videoWidth,
        height: videoElement.videoHeight,
      });
    };
    videoElement.addEventListener("loadedmetadata", updateSourceSize);
    videoElement.addEventListener("resize", updateSourceSize);
    updateSourceSize();

    return () => {
      videoElement.removeEventListener("loadedmetadata", updateSourceSize);
      videoElement.removeEventListener("resize", updateSourceSize);
    };
  }, [videoElement]);

  const renderedMediaRect = useMemo(
    () => calculateRenderedMediaRect(sourceSize, containerSize, objectFit),
    [containerSize, objectFit, sourceSize],
  );

  return { sourceSize, containerSize, renderedMediaRect };
}
