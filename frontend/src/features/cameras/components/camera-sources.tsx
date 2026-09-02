import { Alert02Icon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { AxiosInstance } from "axios";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
import { Spinner } from "@/components/ui/spinner";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cameraDetailQueryOptions } from "@/features/cameras/api/camera-detail-query";
import { cameraQueryKeys } from "@/features/cameras/api/camera-query-keys";
import {
  setDefaultPreviewSource,
  type CameraDetail,
} from "@/features/cameras/api/cameras-api";
import { CameraSourceStatusBadge } from "@/features/cameras/components/camera-status-badge";
import {
  mapDefaultPreviewSourceFailure,
  type DefaultPreviewSourceFeedback,
} from "@/features/cameras/components/default-preview-source-error-mapping";

/**
 * 来源区域直接提交默认源 PATCH，但单选值始终来自 CameraDetail。
 *
 * 请求期间不把用户刚点击的 ID 写入本地状态，因此失败或结果未知时不会显示未经服务端确认的默认源。
 * 列表缓存可能在详情页处于 inactive，所有刷新都必须包含它们，避免返回列表后仍播放旧默认源。
 */
export function CameraSources({
  camera,
  apiClient,
}: {
  camera: CameraDetail;
  apiClient: AxiosInstance;
}) {
  const queryClient = useQueryClient();
  const requestVersionRef = useRef(0);
  const patchPendingRef = useRef(false);
  const [feedback, setFeedback] = useState<DefaultPreviewSourceFeedback>();
  const mutation = useMutation({
    mutationFn: async (sourceId: string) => {
      // 响应只用于确认 PATCH 成功；最终默认 ID 必须来自随后重新读取的列表和详情。
      await setDefaultPreviewSource(
        camera.camera_id,
        { source_id: sourceId },
        apiClient,
      );
    },
    retry: false,
    gcTime: 0,
  });

  function invalidateCameraQueries() {
    return Promise.allSettled([
      queryClient.invalidateQueries({
        queryKey: ["cameras"],
        refetchType: "all",
      }),
      queryClient.invalidateQueries({
        queryKey: cameraQueryKeys.camera(camera.camera_id),
        refetchType: "all",
      }),
    ]);
  }

  async function refreshAfterUnknownResult() {
    const detailOptions = cameraDetailQueryOptions(camera.camera_id, apiClient);
    const results = await Promise.allSettled([
      queryClient.invalidateQueries({
        queryKey: ["cameras"],
        refetchType: "all",
      }),
      // staleTime=0 强制本次调用真正发起 GET；否则刚轮询过的详情会被当作新鲜数据直接返回，
      // 无法确认未知 PATCH 在服务端的最终结果。
      queryClient.fetchQuery({ ...detailOptions, staleTime: 0 }),
    ]);
    return results[1].status === "fulfilled";
  }

  async function changeDefaultSource(sourceId: string) {
    if (
      patchPendingRef.current ||
      sourceId === camera.default_preview_source_id
    ) {
      return;
    }

    const requestVersion = ++requestVersionRef.current;
    // Ref 在 React 提交 disabled 状态前就生效，阻止同一事件循环内的快速重复 change 产生并发 PATCH。
    patchPendingRef.current = true;
    setFeedback(undefined);

    try {
      await mutation.mutateAsync(sourceId);
    } catch (error: unknown) {
      patchPendingRef.current = false;
      let nextFeedback: DefaultPreviewSourceFeedback;
      try {
        nextFeedback = mapDefaultPreviewSourceFailure(error);
      } finally {
        // 即使错误映射发现程序缺陷并继续抛出，也不能把 Mutation variables 留在 cache 中。
        mutation.reset();
      }

      setFeedback(nextFeedback);
      if (nextFeedback.kind === "unknown") {
        const detailConfirmed = await refreshAfterUnknownResult();
        if (detailConfirmed && requestVersionRef.current === requestVersion) {
          setFeedback(undefined);
        }
      }
      return;
    }

    patchPendingRef.current = false;
    mutation.reset();
    toast.success("默认预览源已更新");
    void invalidateCameraQueries();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>摄像头视频源</h2>
        </CardTitle>
        <CardDescription>选择一路信号作为默认预览源</CardDescription>
        <CardAction>
          <div className="flex items-center gap-2">
            {mutation.isPending ? (
              <Spinner aria-label="正在设置默认预览源" />
            ) : null}
            <Badge variant="outline" className="motion-reduce:transition-none">
              {camera.source_count} 路
            </Badge>
          </div>
        </CardAction>
      </CardHeader>
      <CardContent>
        {feedback === undefined ? null : (
          <Alert
            variant={feedback.kind === "error" ? "destructive" : "default"}
            aria-live="assertive"
            className="mb-4"
          >
            <HugeiconsIcon icon={Alert02Icon} strokeWidth={2} />
            <AlertTitle>{feedback.title}</AlertTitle>
            <AlertDescription>{feedback.message}</AlertDescription>
          </Alert>
        )}
        <RadioGroup
          value={camera.default_preview_source_id}
          disabled={mutation.isPending}
          onValueChange={(sourceId) => {
            // Base UI 的回调值在类型层允许宽类型；业务边界只接受响应中使用的字符串 Source ID。
            if (typeof sourceId === "string") {
              void changeDefaultSource(sourceId);
            }
          }}
          aria-label="默认预览源"
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
                      aria-label={`设“${source.name}”为默认预览源`}
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
