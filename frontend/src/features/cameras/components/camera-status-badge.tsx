import { Badge } from "@/components/ui/badge";
import type {
  CameraDetail,
  CameraSourceDetail,
} from "@/features/cameras/api/cameras-api";
import { cn } from "@/lib/utils";

// 状态颜色只引用 Design System 的业务 Token；文字标签同时表达状态，避免只依赖红绿黄。
const STATUS_BADGE_PRESENTATION = {
  ONLINE: {
    label: "在线",
    className: "bg-status-online text-status-online-foreground",
    dotClassName: "bg-status-online-dot",
  },
  DEGRADED: {
    label: "部分离线",
    className: "bg-status-degraded text-status-degraded-foreground",
    dotClassName: "bg-status-degraded-dot",
  },
  OFFLINE: {
    label: "离线",
    className: "bg-status-offline text-status-offline-foreground",
    dotClassName: "bg-status-offline-dot",
  },
} as const satisfies Record<
  CameraDetail["status"],
  { label: string; className: string; dotClassName: string }
>;

function StatusBadge({
  status,
  dataAttribute,
}: {
  status: CameraDetail["status"];
  dataAttribute: "camera" | "source";
}) {
  const presentation = STATUS_BADGE_PRESENTATION[status];
  const dataAttributes =
    dataAttribute === "camera"
      ? { "data-camera-status": true }
      : { "data-source-status": true };

  return (
    <Badge
      {...dataAttributes}
      className={cn(presentation.className, "motion-reduce:transition-none")}
    >
      <span
        data-status-dot
        aria-hidden="true"
        className={cn("size-1.5 rounded-full", presentation.dotClassName)}
      />
      {presentation.label}
    </Badge>
  );
}

export function CameraStatusBadge({ status }: Pick<CameraDetail, "status">) {
  return <StatusBadge status={status} dataAttribute="camera" />;
}

export function CameraSourceStatusBadge({
  status,
}: Pick<CameraSourceDetail, "status">) {
  return <StatusBadge status={status} dataAttribute="source" />;
}
