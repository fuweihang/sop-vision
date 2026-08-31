import { Badge } from "@/components/ui/badge";
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
import { CameraSourceStatusBadge } from "@/features/cameras/components/camera-status-badge";

/**
 * 来源区域沿用原型的信息排列。RadioGroup 是后续切换默认源的占位控件，当前禁用，避免只读详情
 * 误发配置写请求。
 */
export function CameraSources({ camera }: { camera: CameraDetail }) {
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
                    <CameraSourceStatusBadge status={source.status} />
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
