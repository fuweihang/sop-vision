import { useEffect, useRef } from "react";

import { AspectRatio } from "@/components/ui/aspect-ratio";
import { Card, CardContent } from "@/components/ui/card";
import type { CameraDetail } from "@/features/cameras/api/cameras-api";
import { CameraSourceSelect } from "@/features/cameras/components/camera-source-select";
import { VideoControls } from "@/features/video/components/video-controls";
import { VideoSurface } from "@/features/video/components/video-surface";
import { useVideoSurface } from "@/features/video/components/video-surface";
import { useStreamSession } from "@/features/video/stream-session";

type CameraSourceDetail = CameraDetail["sources"][number];

interface CameraDetailPlayerProps {
  source: CameraSourceDetail | null;
  sources: CameraSourceDetail[];
  previewRequested: boolean;
  onSourceChange: (sourceId: string) => void;
}

/**
 * 开始预览和临时切源都应进入实时播放；播放器自己的暂停只在刷新同一路流时保留。协调器只修改
 * 当前 video 的播放意图，不 acquire/release Session。
 */
function CameraPlaybackIntentCoordinator({
  sourceId,
  previewRequested,
}: {
  sourceId: string | null;
  previewRequested: boolean;
}) {
  const {
    actions: { play },
  } = useVideoSurface();
  const previousRef = useRef({ sourceId, previewRequested });

  useEffect(() => {
    const previous = previousRef.current;
    if (
      previewRequested &&
      sourceId !== null &&
      (!previous.previewRequested || previous.sourceId !== sourceId)
    ) {
      void play();
    }
    previousRef.current = { sourceId, previewRequested };
  }, [play, previewRequested, sourceId]);

  return null;
}

/**
 * Camera 只根据用户的预览意图和播放地址决定何时 acquire。页面隐藏不改变用户意图，
 * 因此最小化或切换标签页时保持 Session；WHEP 和媒体 DOM 生命周期仍由 video feature 管理。
 */
export function CameraDetailPlayer({
  sources,
  source,
  previewRequested,
  onSourceChange,
}: CameraDetailPlayerProps) {
  const shouldAcquire = previewRequested && source !== null;
  const session = useStreamSession(
    previewRequested ? (source?.source_id ?? null) : null,
    previewRequested ? (source?.whep_url ?? null) : null,
  );

  let emptyMessage: string | null = null;
  if (source === null) {
    emptyMessage = "当前视频源不可播放";
  } else if (!previewRequested) {
    emptyMessage = "预览已停止";
  }

  return (
    <Card
      role="region"
      aria-label="视频源预览"
      className="overflow-hidden py-0"
    >
      <CardContent className="p-0">
        <AspectRatio ratio={16 / 9} className="bg-muted/50">
          <VideoSurface
            stream={shouldAcquire ? session.stream : null}
            objectFit="contain"
          >
            <CameraPlaybackIntentCoordinator
              sourceId={source?.source_id ?? null}
              previewRequested={previewRequested}
            />
            {emptyMessage !== null && (
              <div className="absolute inset-0 flex items-center justify-center p-6">
                <p className="rounded-md bg-background/85 px-3 py-2 text-center text-sm text-muted-foreground shadow-sm backdrop-blur-sm">
                  {emptyMessage}
                </p>
              </div>
            )}

            {source !== null && (
              <VideoControls
                status={session.status}
                onReconnect={session.reconnect}
                mediaControlsDisabled={!previewRequested}
              >
                <CameraSourceSelect
                  sources={sources}
                  sourceId={source.source_id}
                  onSourceChange={onSourceChange}
                />
              </VideoControls>
            )}
          </VideoSurface>
        </AspectRatio>
      </CardContent>
    </Card>
  );
}
