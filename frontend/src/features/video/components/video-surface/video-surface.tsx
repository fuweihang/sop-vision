import {
  type PropsWithChildren,
  useCallback,
  useMemo,
  useRef,
  useState,
} from "react";

import { useVideoFullscreen } from "@/features/video/components/video-surface/use-video-fullscreen";
import { useVideoLayout } from "@/features/video/components/video-surface/use-video-layout";
import { useVideoPageFullscreen } from "@/features/video/components/video-surface/use-video-page-fullscreen";
import { useVideoPlayback } from "@/features/video/components/video-surface/use-video-playback";
import { useVideoPresentation } from "@/features/video/components/video-surface/use-video-presentation";
import {
  type VideoSurfaceContextValue,
  VideoSurfaceContext,
} from "@/features/video/components/video-surface/video-surface-context";
import type { VideoObjectFit } from "@/features/video/geometry/video-geometry";
import { cn } from "@/lib/utils";

interface VideoSurfaceProps extends PropsWithChildren {
  stream: MediaStream | null;
  objectFit: VideoObjectFit;
  className?: string;
}

/**
 * 通用媒体表面的公共组合入口。浏览器媒体行为由同目录 hooks 管理，这里只装配 video、children
 * overlay 和受控 Context，不包含 Camera、Card、Detail 或 Detection 业务规则。
 */
export function VideoSurface({
  stream,
  objectFit,
  className,
  children,
}: VideoSurfaceProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [videoElement, setVideoElement] = useState<HTMLVideoElement | null>(
    null,
  );
  const [containerElement, setContainerElement] =
    useState<HTMLDivElement | null>(null);

  const setVideoRef = useCallback((element: HTMLVideoElement | null) => {
    if (element !== null) {
      // volume 不是可靠的 HTML attribute。必须在首次 play() 之前写入属性，保证默认静音时
      // 实际音量和操作栏 Slider 都从 0 开始。
      element.volume = 0;
    }
    videoRef.current = element;
    setVideoElement(element);
  }, []);
  const setContainerRef = useCallback((element: HTMLDivElement | null) => {
    setContainerElement(element);
  }, []);

  const layout = useVideoLayout({
    videoElement,
    containerElement,
    objectFit,
  });
  const playback = useVideoPlayback({ videoRef, videoElement, stream });
  const presentation = useVideoPresentation({
    videoElement,
    stream,
    paused: playback.state.paused,
  });
  const fullscreen = useVideoFullscreen(containerElement);
  const {
    state: { canFullscreen, isFullscreen },
    actions: {
      requestFullscreen: requestNativeFullscreen,
      exitFullscreen: exitNativeFullscreen,
    },
  } = fullscreen;
  const pageFullscreen = useVideoPageFullscreen();
  const {
    state: { isPageFullscreen },
    actions: { requestPageFullscreen: enterPageFullscreen, exitPageFullscreen },
  } = pageFullscreen;

  const requestFullscreen = useCallback(async () => {
    // 两种显示模式不能叠加。先退出网页全屏，再让同一个容器进入浏览器全屏。
    exitPageFullscreen();
    await requestNativeFullscreen();
  }, [exitPageFullscreen, requestNativeFullscreen]);
  const toggleFullscreen = useCallback(async () => {
    if (isFullscreen) {
      await exitNativeFullscreen();
      return;
    }
    await requestFullscreen();
  }, [exitNativeFullscreen, isFullscreen, requestFullscreen]);
  const requestPageFullscreen = useCallback(async () => {
    // 从浏览器全屏切换时必须等待 Fullscreen API 退出完成，随后网页布局才接管 viewport。
    if (isFullscreen) {
      await exitNativeFullscreen();
    }
    enterPageFullscreen();
  }, [enterPageFullscreen, exitNativeFullscreen, isFullscreen]);
  const togglePageFullscreen = useCallback(async () => {
    if (isPageFullscreen) {
      exitPageFullscreen();
      return;
    }
    await requestPageFullscreen();
  }, [exitPageFullscreen, isPageFullscreen, requestPageFullscreen]);
  // MediaStream 可能原地增加音频 Track；数量参与 Context 依赖，组件一旦因流状态更新而重渲染，
  // controls 就会读取当前 Track 状态，而不是缓存创建 Stream 时的结果。
  const audioTrackCount = stream?.getAudioTracks().length ?? 0;

  const context = useMemo<VideoSurfaceContextValue>(
    () => ({
      state: {
        sourceSize: layout.sourceSize,
        containerSize: layout.containerSize,
        renderedMediaRect: layout.renderedMediaRect,
        hasAudio: audioTrackCount > 0,
        hasPresentedFrame: presentation.hasPresentedFrame,
        paused: playback.state.paused,
        muted: playback.state.muted,
        volume: playback.state.volume,
        canFullscreen,
        isFullscreen,
        isPageFullscreen,
        playbackError: playback.state.playbackError,
        presentationError: presentation.presentationError,
      },
      actions: {
        play: playback.actions.play,
        pause: playback.actions.pause,
        togglePlayback: playback.actions.togglePlayback,
        setMuted: playback.actions.setMuted,
        setVolume: playback.actions.setVolume,
        requestFullscreen,
        exitFullscreen: exitNativeFullscreen,
        toggleFullscreen,
        requestPageFullscreen,
        exitPageFullscreen,
        togglePageFullscreen,
      },
      meta: { videoElement, containerElement },
    }),
    [
      audioTrackCount,
      containerElement,
      canFullscreen,
      exitNativeFullscreen,
      exitPageFullscreen,
      isPageFullscreen,
      requestFullscreen,
      requestPageFullscreen,
      toggleFullscreen,
      togglePageFullscreen,
      isFullscreen,
      layout.containerSize,
      layout.renderedMediaRect,
      layout.sourceSize,
      playback.actions.pause,
      playback.actions.play,
      playback.actions.setMuted,
      playback.actions.setVolume,
      playback.actions.togglePlayback,
      playback.state.muted,
      playback.state.paused,
      playback.state.playbackError,
      playback.state.volume,
      presentation.hasPresentedFrame,
      presentation.presentationError,
      videoElement,
    ],
  );

  return (
    <VideoSurfaceContext value={context}>
      <div
        ref={setContainerRef}
        className={cn(
          "relative size-full overflow-hidden bg-muted",
          isPageFullscreen && "fixed inset-0 z-50 h-svh w-screen",
          className,
        )}
      >
        <video
          ref={setVideoRef}
          autoPlay
          muted
          playsInline
          controls={false}
          aria-label="实时视频"
          className={cn(
            "absolute inset-0 size-full",
            objectFit === "cover" ? "object-cover" : "object-contain",
          )}
        />
        <div className="pointer-events-none absolute inset-0">{children}</div>
      </div>
    </VideoSurfaceContext>
  );
}
