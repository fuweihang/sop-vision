import { queryOptions } from "@tanstack/react-query";
import type { AxiosInstance } from "axios";

import { cameraQueryKeys } from "@/features/cameras/api/camera-query-keys";
import {
  listCameras,
  type NormalizedCameraListQuery,
} from "@/features/cameras/api/cameras-api";
import { ApiProblemError, ApiTransportError } from "@/lib/api-errors";

export const CAMERA_LIST_STALE_TIME = 15_000;
export const CAMERA_LIST_GC_TIME = 5 * 60_000;
export const CAMERA_LIST_REFETCH_INTERVAL = 15_000;

/**
 * 列表只重试可能短暂恢复的读取失败，并且最多自动补发一次。
 *
 * 422、聚合损坏、无法识别的响应和程序错误继续交给页面错误状态，避免重复请求掩盖
 * 确定性问题。`failureCount` 在第一次失败时为 0，因此 `< 1` 表示只允许一次重试。
 */
export function shouldRetryCameraListQuery(
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
 * 列表 loader 和页面订阅共用此工厂，保证 URL、Query Key、HTTP 参数和刷新周期一致。
 * Query cache 只保存在当前浏览器会话内存中，不接入任何持久化存储。
 */
export function cameraListQueryOptions(
  query: NormalizedCameraListQuery,
  apiClient: AxiosInstance,
) {
  return queryOptions({
    queryKey: cameraQueryKeys.cameras(query),
    queryFn: () => listCameras(query, apiClient),
    staleTime: CAMERA_LIST_STALE_TIME,
    gcTime: CAMERA_LIST_GC_TIME,
    refetchInterval: CAMERA_LIST_REFETCH_INTERVAL,
    refetchIntervalInBackground: false,
    retry: shouldRetryCameraListQuery,
  });
}
