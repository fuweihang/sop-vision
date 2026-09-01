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
  CameraSummary,
  NormalizedCameraListQuery,
} from "@/features/cameras/api/cameras-api";
import { CameraCardPreview } from "@/features/cameras/components/camera-card-preview";
import { CameraStatusBadge } from "@/features/cameras/components/camera-status-badge";

interface CameraListCardProps {
  camera: CameraSummary;
  search: NormalizedCameraListQuery;
}

/**
 * 列表 Card 只读取 CameraSummary 的非敏感字段。
 *
 * 详情 Link 显式携带当前搜索和分页参数，保证用户查看详情后可恢复原列表位置。媒体区域只把列表
 * 返回的默认 Source 交给预览组件，不读取 CameraDetail 或任何敏感连接字段。
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
            <CameraCardPreview source={camera.default_preview_source} />
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
