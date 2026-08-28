import { queryOptions } from "@tanstack/react-query";
import type { AxiosInstance } from "axios";

import { cameraQueryKeys } from "@/features/cameras/api/camera-query-keys";
import { getCamera } from "@/features/cameras/api/cameras-api";
import { ApiProblemError, ApiTransportError } from "@/lib/api-errors";

export const CAMERA_DETAIL_STALE_TIME = 15_000;
export const CAMERA_DETAIL_GC_TIME = 5 * 60_000;
export const CAMERA_DETAIL_REFETCH_INTERVAL = 15_000;

/**
 * Camera 详情只重试明确可恢复的读取失败。
 *
 * `failureCount` 在第一次失败时为 0，因此 `< 1` 表示最多再发起一次请求。404、422、损坏聚合、
 * 非法响应和未知程序错误都不会因自动重试而增加等待时间或重复暴露敏感详情。
 */
export function shouldRetryCameraDetailQuery(
  failureCount: number,
  error: unknown,
) {
  if (failureCount >= 1) {
    return false;
  }

  if (error instanceof ApiTransportError) {
    return true;
  }

  return (
    error instanceof ApiProblemError &&
    error.problem.status === 503 &&
    error.problem.code === "DATABASE_UNAVAILABLE"
  );
}

/**
 * 详情 loader 与页面订阅必须调用同一个工厂，才能共享 Query Key、刷新周期和注入的 HTTP Client。
 * 工厂不创建生产 Client，也不把含密码和 RTSP URL 的详情写入任何持久化存储。
 */
export function cameraDetailQueryOptions(
  cameraId: string,
  apiClient: AxiosInstance,
) {
  return queryOptions({
    queryKey: cameraQueryKeys.camera(cameraId),
    queryFn: () => getCamera(cameraId, apiClient),
    staleTime: CAMERA_DETAIL_STALE_TIME,
    gcTime: CAMERA_DETAIL_GC_TIME,
    refetchInterval: CAMERA_DETAIL_REFETCH_INTERVAL,
    refetchIntervalInBackground: false,
    retry: shouldRetryCameraDetailQuery,
  });
}
