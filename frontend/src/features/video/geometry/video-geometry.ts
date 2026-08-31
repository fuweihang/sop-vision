export interface VideoSize {
  width: number;
  height: number;
}

export interface RenderedMediaRect extends VideoSize {
  x: number;
  y: number;
}

export type VideoObjectFit = "cover" | "contain";

/**
 * 计算源视频经过 object-fit 后在容器中的实际区域。Detection overlay 后续可以直接使用这个纯函数，
 * 无需依赖 React Context 或 VideoSurface 的 DOM 结构。
 */
export function calculateRenderedMediaRect(
  source: VideoSize,
  container: VideoSize,
  objectFit: VideoObjectFit,
): RenderedMediaRect {
  if (
    source.width <= 0 ||
    source.height <= 0 ||
    container.width <= 0 ||
    container.height <= 0
  ) {
    return { x: 0, y: 0, width: 0, height: 0 };
  }

  const scale =
    objectFit === "contain"
      ? Math.min(
          container.width / source.width,
          container.height / source.height,
        )
      : Math.max(
          container.width / source.width,
          container.height / source.height,
        );
  const width = source.width * scale;
  const height = source.height * scale;

  return {
    x: (container.width - width) / 2,
    y: (container.height - height) / 2,
    width,
    height,
  };
}
