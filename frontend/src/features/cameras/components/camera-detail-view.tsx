import {
  AlertCircleIcon,
  Delete02Icon,
  Edit02Icon,
  PlayIcon,
  ViewIcon,
  ViewOffSlashIcon,
} from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { useState } from "react";

import { PageContainer } from "@/components/layout/page-container";
import { PageHeader } from "@/components/layout/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AspectRatio } from "@/components/ui/aspect-ratio";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { CameraDetail } from "@/features/cameras/api/cameras-api";
import { cn } from "@/lib/utils";

type CameraSourceDetail = CameraDetail["sources"][number];

const timestampFormatter = new Intl.DateTimeFormat("zh-CN", {
  dateStyle: "medium",
  timeStyle: "medium",
});

const MASKED_PASSWORD = "********";

// 密码行包含图标按钮，会比纯文本行更高；所有连接信息行共用垂直居中和水平留白，
// 避免标签在较高行中贴上沿，也避免字段文字紧贴 CardContent 边缘。
const CONNECTION_INFORMATION_ROW_CLASS_NAME =
  "grid min-w-0 grid-cols-[6rem_minmax(0,1fr)] items-center gap-3 px-2 py-3";

// 状态颜色只引用 Design System 的业务语义 Token；文字标签同时表达状态，避免只依赖红绿黄。
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

function formatTimestamp(value: string) {
  return timestampFormatter.format(new Date(value));
}

function CameraStatusBadge({ status }: Pick<CameraDetail, "status">) {
  const presentation = STATUS_BADGE_PRESENTATION[status];

  return (
    <Badge
      data-camera-status
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

function Timestamp({ value }: { value: string }) {
  return <time dateTime={value}>{formatTimestamp(value)}</time>;
}

/**
 * 密码默认不进入可见 DOM，避免旁观者在打开详情时直接看到凭据。
 * 用户主动点击眼睛按钮后才渲染明文；再次隐藏时恢复固定星号，不暴露密码长度。
 */
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

function ConnectionInformation({
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

/**
 * 06 只保留后续播放器需要的 16:9 区域。
 * 布局只显示左下角默认源名称，不创建 video 或 PeerConnection。
 */
function ReadonlyPreview({ source }: { source: CameraSourceDetail }) {
  return (
    <Card
      role="region"
      aria-label="默认视频源预览"
      className="overflow-hidden py-0"
    >
      <CardContent className="p-0">
        <AspectRatio ratio={16 / 9} className="bg-muted/50">
          <div className="absolute inset-0 flex min-w-0 items-end p-4 sm:p-6">
            <h2 className="text-balance wrap-break-word font-medium">
              {source.name}
            </h2>
          </div>
        </AspectRatio>
      </CardContent>
    </Card>
  );
}

function SourceStatusBadge({ status }: Pick<CameraSourceDetail, "status">) {
  const presentation = STATUS_BADGE_PRESENTATION[status];

  return (
    <Badge
      data-source-status
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

/**
 * 来源区域沿用原型的信息排列：默认源选择、名称、完整 RTSP URL、状态。
 * RadioGroup 是后续切换默认源的占位控件，当前禁用，避免只读详情误发配置写请求。
 */
function CameraSources({ camera }: { camera: CameraDetail }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>摄像头视频源</h2>
        </CardTitle>
        <CardDescription>选择一路信号作为默认预览源</CardDescription>
        <CardAction>
          <Badge variant="outline" className="motion-reduce:transition-none">
            {camera.source_count} 路
          </Badge>
        </CardAction>
      </CardHeader>
      <CardContent>
        <RadioGroup
          value={camera.default_preview_source_id}
          disabled
          aria-label="默认预览源（切换功能暂未实现）"
          className="gap-0"
        >
          <Table className="min-w-3xl">
            <TableHeader>
              <TableRow>
                <TableHead className="w-20 px-4 text-center">预览</TableHead>
                <TableHead className="px-4">源名称</TableHead>
                <TableHead className="px-4">RTSP URL</TableHead>
                <TableHead className="w-52 px-4 text-center">状态</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {camera.sources.map((source) => (
                <TableRow key={source.source_id}>
                  <TableCell className="px-4">
                    <RadioGroupItem
                      id={`camera-source-${source.source_id}`}
                      value={source.source_id}
                      className="mx-auto"
                      aria-label={`设“${source.name}”为默认预览源（功能暂未实现）`}
                    />
                  </TableCell>
                  <TableCell className="px-4 font-medium">
                    {source.name}
                  </TableCell>
                  <TableCell className="min-w-96 px-4 whitespace-normal">
                    <code className="block break-all font-mono text-xs leading-relaxed">
                      {source.rtsp_url}
                    </code>
                  </TableCell>
                  <TableCell className="px-4 text-center">
                    <SourceStatusBadge status={source.status} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </RadioGroup>
      </CardContent>
    </Card>
  );
}

function PlaceholderActions() {
  return (
    <>
      <span id="camera-detail-placeholder-actions" className="sr-only">
        开始预览和编辑摄像头功能暂未实现
      </span>
      <Button
        type="button"
        variant="outline"
        disabled
        aria-describedby="camera-detail-placeholder-actions"
      >
        <HugeiconsIcon
          icon={PlayIcon}
          strokeWidth={2}
          data-icon="inline-start"
        />
        开始预览
      </Button>
      <Button
        type="button"
        variant="outline"
        disabled
        aria-describedby="camera-detail-placeholder-actions"
      >
        <HugeiconsIcon
          icon={Edit02Icon}
          strokeWidth={2}
          data-icon="inline-start"
        />
        编辑摄像头
      </Button>
    </>
  );
}

function DestructiveSection() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>删除摄像头</h2>
        </CardTitle>
        <CardDescription>仅在没有检测任务引用时可删除。</CardDescription>
        <CardAction className="self-center">
          <Button type="button" variant="destructive" disabled>
            <HugeiconsIcon
              icon={Delete02Icon}
              strokeWidth={2}
              data-icon="inline-start"
            />
            删除摄像头
          </Button>
        </CardAction>
      </CardHeader>
    </Card>
  );
}

/** Camera 详情页面；原型只提供区域顺序和排列参考，视觉全部沿用项目 Design System。 */
export function CameraDetailView({ camera }: { camera: CameraDetail }) {
  const defaultSource = camera.sources.find(
    (source) => source.source_id === camera.default_preview_source_id,
  );

  if (defaultSource === undefined) {
    // Backend 聚合和 Schema 正常情况下不会触发；防御分支避免损坏响应静默显示错误默认源。
    return (
      <PageContainer>
        <PageHeader
          title={camera.name}
          description="摄像头详情暂时无法完整显示。"
        />
        <Alert variant="destructive" className="max-w-2xl">
          <HugeiconsIcon icon={AlertCircleIcon} strokeWidth={2} />
          <AlertTitle>默认预览源无效</AlertTitle>
          <AlertDescription>
            当前详情没有匹配的默认预览源，请稍后重试。
          </AlertDescription>
        </Alert>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <PageHeader
        title={camera.name}
        description="摄像头连接信息与默认预览"
        actions={<PlaceholderActions />}
        className="sm:items-center"
        actionsClassName="self-end sm:self-auto"
      />
      <div className="grid min-w-0 items-start gap-6 min-[1200px]:grid-cols-[minmax(0,1.65fr)_minmax(18rem,0.75fr)]">
        <ReadonlyPreview source={defaultSource} />
        <ConnectionInformation camera={camera} defaultSource={defaultSource} />
      </div>
      <CameraSources camera={camera} />
      <DestructiveSection />
    </PageContainer>
  );
}
