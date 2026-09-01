import { ViewIcon, ViewOffSlashIcon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type {
  CameraDetail,
  CameraSourceDetail,
} from "@/features/cameras/api/cameras-api";
import { CameraStatusBadge } from "@/features/cameras/components/camera-status-badge";
import { cn } from "@/lib/utils";

const timestampFormatter = new Intl.DateTimeFormat("zh-CN", {
  dateStyle: "medium",
  timeStyle: "medium",
});
const MASKED_PASSWORD = "********";

// 密码行包含图标按钮，会比纯文本行更高；所有连接信息行共用垂直居中和水平留白。
const CONNECTION_INFORMATION_ROW_CLASS_NAME =
  "grid min-w-0 grid-cols-[6rem_minmax(0,1fr)] items-center gap-3 px-2 py-3";

function Timestamp({ value }: { value: string }) {
  return (
    <time dateTime={value}>{timestampFormatter.format(new Date(value))}</time>
  );
}

/** 密码默认不进入可见 DOM；用户主动点击后才显示，再次隐藏时恢复固定星号。 */
function PasswordValue({ password }: Pick<CameraDetail, "password">) {
  const [isVisible, setIsVisible] = useState(false);
  const actionLabel = isVisible ? "隐藏密码" : "显示密码";

  return (
    <div className="flex min-w-0 items-center justify-between gap-2">
      <span className="min-w-0 break-all font-mono text-xs">
        {isVisible ? password : MASKED_PASSWORD}
      </span>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        aria-label={actionLabel}
        aria-pressed={isVisible}
        onClick={() => setIsVisible((current) => !current)}
      >
        <HugeiconsIcon
          icon={isVisible ? ViewIcon : ViewOffSlashIcon}
          strokeWidth={2}
          data-icon="inline-start"
        />
      </Button>
    </div>
  );
}

export function CameraConnectionInformation({
  camera,
  defaultSource,
}: {
  camera: CameraDetail;
  defaultSource: CameraSourceDetail;
}) {
  const fields = [
    { label: "IPv4 地址", value: camera.ip_address, mono: true },
    { label: "RTSP 端口", value: String(camera.rtsp_port), mono: true },
    { label: "用户名", value: camera.username, mono: false },
  ] as const;

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>连接信息</h2>
        </CardTitle>
        <CardDescription>当前保存的设备连接参数</CardDescription>
        <CardAction className="self-center">
          <CameraStatusBadge status={camera.status} />
        </CardAction>
      </CardHeader>
      <CardContent>
        <dl className="flex flex-col">
          {fields.map((field) => (
            <div
              key={field.label}
              className={cn(CONNECTION_INFORMATION_ROW_CLASS_NAME, "border-b")}
            >
              <dt className="text-muted-foreground">{field.label}</dt>
              <dd
                className={cn(
                  "min-w-0 break-all",
                  field.mono && "font-mono text-xs",
                )}
              >
                {field.value}
              </dd>
            </div>
          ))}
          <div
            className={cn(CONNECTION_INFORMATION_ROW_CLASS_NAME, "border-b")}
          >
            <dt className="text-muted-foreground">密码</dt>
            <dd className="min-w-0">
              <PasswordValue password={camera.password} />
            </dd>
          </div>
          <div className={CONNECTION_INFORMATION_ROW_CLASS_NAME}>
            <dt className="text-muted-foreground">最近检查</dt>
            <dd className="min-w-0 wrap-break-word">
              <Timestamp value={defaultSource.last_checked_at} />
            </dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  );
}
