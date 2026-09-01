import { Camera01Icon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { Link } from "@tanstack/react-router";

import { AspectRatio } from "@/components/ui/aspect-ratio";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type {
  CameraPage,
  NormalizedCameraListQuery,
} from "@/features/cameras/api/cameras-api";
import { CameraStatusBadge } from "@/features/cameras/components/camera-status-badge";

type CameraSummary = CameraPage["items"][number];

interface CameraListCardProps {
  camera: CameraSummary;
  search: NormalizedCameraListQuery;
}

/**
 * 列表 Card 只读取 CameraSummary 的非敏感字段。
 *
 * 详情 Link 显式携带当前搜索和分页参数，保证用户查看详情后可恢复原列表位置；这里不读取
 * `whep_url`，也不创建 video 或 Stream Session，实时预览由后续任务负责。
 */
export function CameraListCard({ camera, search }: CameraListCardProps) {
  return (
    <Link
      to="/cameras/$cameraId"
      params={{ cameraId: camera.camera_id }}
      search={search}
      preload="intent"
      className="group/camera-link block min-w-0 rounded-xl outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
      aria-label={`查看摄像头详情：${camera.name}`}
    >
      <Card className="h-full min-w-0 gap-0 py-0 transition-shadow group-hover/camera-link:ring-foreground/20 motion-reduce:transition-none">
        <CardContent className="p-0">
          <AspectRatio
            ratio={16 / 9}
            data-camera-preview
            className="isolate grid place-items-center overflow-hidden bg-overlay-control-surface text-overlay-control-foreground"
          >
            {/* 03 会在这个固定比例区域装配 VideoSurface；当前静态图标明确表示尚未建立媒体会话。 */}
            <HugeiconsIcon
              icon={Camera01Icon}
              strokeWidth={1.5}
              aria-hidden="true"
              className="size-10 opacity-20"
            />
            <div
              aria-hidden="true"
              className="pointer-events-none absolute inset-x-0 bottom-0 h-1/2 bg-linear-to-t from-overlay-control-surface/90 to-transparent"
            />
            <span className="absolute right-3 bottom-3 left-3 truncate text-xs font-medium">
              {camera.default_preview_source.name}
            </span>
          </AspectRatio>
        </CardContent>
        <CardHeader className="gap-1 py-4">
          <CardTitle className="min-w-0">
            <h2 className="truncate">{camera.name}</h2>
          </CardTitle>
          <CardDescription className="truncate font-mono text-xs">
            {camera.ip_address}:{camera.rtsp_port}
          </CardDescription>
          <CardAction>
            <CameraStatusBadge status={camera.status} />
          </CardAction>
        </CardHeader>
        <CardContent className="pb-4 text-xs text-muted-foreground">
          {camera.online_source_count} / {camera.source_count} 路在线
        </CardContent>
      </Card>
    </Link>
  );
}
