import { useEffect, useState } from "react";

const FIRST_FRAME_TIMEOUT_MESSAGE = "视频画面加载超时，请刷新当前流。";
const FIRST_FRAME_TIMEOUT_MS = 10_000;

interface UseVideoPresentationOptions {
  videoElement: HTMLVideoElement | null;
  stream: MediaStream | null;
  paused: boolean;
}

/** 等待当前 Stream 的首帧真正进入浏览器渲染流程，并为无法解码的流设置等待上限。 */
export function useVideoPresentation({
  videoElement,
  stream,
  paused,
}: UseVideoPresentationOptions) {
  const [presentedStream, setPresentedStream] = useState<MediaStream | null>(
    null,
  );
  const [presentationFailure, setPresentationFailure] = useState<{
    stream: MediaStream;
    message: string;
  } | null>(null);
  const videoTrackCount = stream?.getVideoTracks().length ?? 0;

  useEffect(() => {
    if (videoElement === null || stream === null || videoTrackCount === 0) {
      return;
    }

    const markCurrentStreamPresented = () => {
      // 换流后旧回调仍可能进入任务队列。只有 video 仍绑定原 Stream 时才能结束它的 loading。
      if (videoElement.srcObject !== stream) {
        return;
      }
      setPresentedStream(stream);
      setPresentationFailure(null);
    };

    if (typeof videoElement.requestVideoFrameCallback === "function") {
      // 该回调在视频帧提交给浏览器合成流程时触发，比 playing/canplay 更接近用户看到画面的时刻。
      const callbackId = videoElement.requestVideoFrameCallback(
        markCurrentStreamPresented,
      );
      return () => {
        // 不完整的 WebView polyfill 可能只提供 request，清理前仍需检查 cancel 能力。
        videoElement.cancelVideoFrameCallback?.(callbackId);
      };
    }

    // Safari 旧版本等不支持 requestVideoFrameCallback；loadeddata 至少表示当前帧数据已可用。
    videoElement.addEventListener("loadeddata", markCurrentStreamPresented);
    if (videoElement.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
      markCurrentStreamPresented();
    }
    return () =>
      videoElement.removeEventListener(
        "loadeddata",
        markCurrentStreamPresented,
      );
  }, [stream, videoElement, videoTrackCount]);

  const hasPresentedFrame = stream !== null && presentedStream === stream;

  useEffect(() => {
    if (
      videoElement === null ||
      stream === null ||
      videoTrackCount === 0 ||
      hasPresentedFrame ||
      paused
    ) {
      return;
    }

    // Track 到达不代表关键帧可解码。只在播放意图下计时；用户暂停时没有新帧是预期行为。
    const timeoutId = window.setTimeout(() => {
      if (videoElement.srcObject === stream) {
        setPresentationFailure({
          stream,
          message: FIRST_FRAME_TIMEOUT_MESSAGE,
        });
      }
    }, FIRST_FRAME_TIMEOUT_MS);
    return () => window.clearTimeout(timeoutId);
  }, [hasPresentedFrame, paused, stream, videoElement, videoTrackCount]);

  return {
    hasPresentedFrame,
    presentationError:
      stream !== null && presentationFailure?.stream === stream
        ? presentationFailure.message
        : null,
  };
}
