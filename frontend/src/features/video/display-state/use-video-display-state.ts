import { useVideoSurface } from "@/features/video/components/video-surface";
import {
  deriveVideoDisplayState,
  type VideoDisplayState,
} from "@/features/video/display-state/video-display-state";
import type { StreamSessionStatus } from "@/features/video/stream-session/stream-session";

interface UseVideoDisplayStateInput {
  previewActive: boolean;
  sessionStatus: StreamSessionStatus;
}

/**
 * 把当前 VideoSurface 的 DOM 结果接入共享展示状态规则。
 *
 * Card 与 Detail 必须经过这个 Hook，避免分别维护暂停、首帧和媒体错误的字段映射。纯状态优先级仍由
 * `deriveVideoDisplayState` 负责，因此不依赖 React 的规则可以继续单独测试。
 */
export function useVideoDisplayState({
  previewActive,
  sessionStatus,
}: UseVideoDisplayStateInput): VideoDisplayState {
  const { state } = useVideoSurface();

  return deriveVideoDisplayState({
    previewActive,
    sessionStatus,
    hasPresentedFrame: state.hasPresentedFrame,
    frameWaitActive: !state.paused,
    playbackError: state.playbackError,
    presentationError: state.presentationError,
  });
}
