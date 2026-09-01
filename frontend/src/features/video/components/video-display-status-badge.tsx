import { Badge } from "@/components/ui/badge";
import type { VideoDisplayState } from "@/features/video/display-state";
import type { StreamSessionStatus } from "@/features/video/stream-session/stream-session";

interface VideoDisplayStatusBadgeProps {
  sessionStatus: StreamSessionStatus;
  displayState: VideoDisplayState;
}

/**
 * Card 与 Detail 共用的有效视频状态 Badge。不可预览属于 Camera 的空 URL 规则，不进入本组件。
 */
export function VideoDisplayStatusBadge({
  sessionStatus,
  displayState,
}: VideoDisplayStatusBadgeProps) {
  return (
    <Badge
      variant="overlay"
      data-stream-session-status={sessionStatus}
      data-video-display-status={displayState.status}
    >
      {displayState.label}
    </Badge>
  );
}
