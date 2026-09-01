import { Camera01Icon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import type { CameraDefaultPreviewSource } from "@/features/cameras/api/cameras-api";
import { VideoDisplayStatusBadge } from "@/features/video/components/video-display-status-badge";
import { VideoSurface } from "@/features/video/components/video-surface";
import {
  type StreamSessionStatus,
  useStreamSession,
} from "@/features/video/stream-session";
import { useVideoDisplayState } from "@/features/video/display-state";

interface CameraCardPreviewOverlayProps {
  source: CameraDefaultPreviewSource;
  statusBadge: ReactNode;
  loadingMessage: string | null;
}

/**
 * Card overlay 在左上角显示当前浏览器 Session 状态，在底部显示默认 Source 名称。
 * Camera 和 Source 的 Backend 状态不放进媒体画面，避免一张 Card 同时出现过多状态标签。
 */
function CameraCardPreviewOverlay({
  source,
  statusBadge,
  loadingMessage,
}: CameraCardPreviewOverlayProps) {
  return (
    <>
      <div
        aria-hidden="true"
        className="absolute inset-x-0 bottom-0 h-1/2 bg-linear-to-t from-overlay-control-surface/90 to-transparent"
      />
      <div className="absolute top-3 left-3">{statusBadge}</div>
      {loadingMessage !== null && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center p-4">
          <div className="rounded-full bg-overlay-control-surface/70 p-2 text-overlay-control-foreground shadow-sm backdrop-blur-sm">
            <Spinner className="size-5" aria-label={loadingMessage} />
          </div>
        </div>
      )}
      <span
        title={source.name}
        className="absolute right-3 bottom-3 left-3 truncate text-xs font-medium"
      >
        {source.name}
      </span>
    </>
  );
}

/** Card 的展示状态属于当前 video DOM；即使共享 MediaStream，也必须独立等待各自的首帧。 */
function CameraCardLiveOverlay({
  source,
  sessionStatus,
}: {
  source: CameraDefaultPreviewSource;
  sessionStatus: StreamSessionStatus;
}) {
  const displayState = useVideoDisplayState({
    previewActive: true,
    sessionStatus,
  });

  return (
    <CameraCardPreviewOverlay
      source={source}
      statusBadge={
        <VideoDisplayStatusBadge
          sessionStatus={sessionStatus}
          displayState={displayState}
        />
      }
      loadingMessage={displayState.loading?.message ?? null}
    />
  );
}

/** 有播放地址的 Card 在挂载期间始终持有 Lease，不受滚动位置或页面 hidden 状态影响。 */
function CameraCardLivePreview({
  source,
}: {
  source: CameraDefaultPreviewSource;
}) {
  // 父组件只在 URL 非空时挂载本组件，因此这里不需要额外的可见性 hook 或空值状态机。
  const session = useStreamSession(source.source_id, source.whep_url);

  return (
    <VideoSurface stream={session.stream} objectFit="cover">
      <CameraCardLiveOverlay source={source} sessionStatus={session.status} />
    </VideoSurface>
  );
}

/**
 * Camera Card 的媒体区域只读取列表返回的默认 Source，不请求敏感详情，也不选择备用 Source。
 * URL 缺失时不创建 video，避免无媒体来源的 DOM 暗示当前存在可播放会话。
 */
export function CameraCardPreview({
  source,
}: {
  source: CameraDefaultPreviewSource;
}) {
  if (source.whep_url === null) {
    return (
      <div className="relative grid size-full place-items-center">
        <HugeiconsIcon
          icon={Camera01Icon}
          strokeWidth={1.5}
          aria-hidden="true"
          className="size-10 opacity-20"
        />
        <CameraCardPreviewOverlay
          source={source}
          statusBadge={
            <Badge
              variant="overlay"
              data-stream-session-status="unavailable"
              data-video-display-status="unavailable"
            >
              不可预览
            </Badge>
          }
          loadingMessage={null}
        />
      </div>
    );
  }

  return <CameraCardLivePreview source={source} />;
}
