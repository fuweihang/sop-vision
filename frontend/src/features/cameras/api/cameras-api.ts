import type { AxiosInstance } from "axios";

import type { operations } from "@/generated/openapi";
import { apiClient } from "@/lib/api-client";

/** Camera Feature 的类型安全 HTTP 边界；测试可注入独立 Axios Client。 */

export type CameraListQuery = NonNullable<
  operations["listCameras"]["parameters"]["query"]
>;
export type NormalizedCameraListQuery = Readonly<{
  q: string | undefined;
  page: number;
  page_size: number;
}>;

export type CameraPage =
  operations["listCameras"]["responses"][200]["content"]["application/json"];
export type CameraDetail =
  operations["getCamera"]["responses"][200]["content"]["application/json"];
export type CameraCreateRequest =
  operations["createCamera"]["requestBody"]["content"]["application/json"];
export type CameraUpdateRequest =
  operations["updateCamera"]["requestBody"]["content"]["application/json"];
export type SetDefaultPreviewSourceRequest =
  operations["setDefaultPreviewSource"]["requestBody"]["content"]["application/json"];
export type DefaultPreviewSourceResponse =
  operations["setDefaultPreviewSource"]["responses"][200]["content"]["application/json"];
export type PlaybackInfo =
  operations["prepareCameraSourcePlayback"]["responses"][200]["content"]["application/json"];

const DEFAULT_PAGE = 1;
const DEFAULT_PAGE_SIZE = 20;

/**
 * 让 HTTP 参数和 Query Key 共用同一规范化结果。
 *
 * 空 q 必须等同未提供；显式保留 q 属性为 undefined，使冻结的 Key 形状始终是
 * `{ q, page, page_size }`，TanStack Query 的稳定哈希也会把它与缺省 q 视为同一查询。
 */
export function normalizeCameraListQuery(
  query: CameraListQuery = {},
): NormalizedCameraListQuery {
  const trimmedQuery = query.q?.trim();
  return {
    q:
      trimmedQuery === "" || trimmedQuery === undefined
        ? undefined
        : trimmedQuery,
    page: query.page ?? DEFAULT_PAGE,
    page_size: query.page_size ?? DEFAULT_PAGE_SIZE,
  };
}

/** Cameras operation 调用全部复用唯一生产 Axios Client，并允许测试注入隔离实例。 */
export async function listCameras(
  query: CameraListQuery = {},
  client: AxiosInstance = apiClient,
): Promise<CameraPage> {
  const response = await client.get<CameraPage>("/cameras", {
    params: normalizeCameraListQuery(query),
  });
  return response.data;
}

export async function createCamera(
  request: CameraCreateRequest,
  client: AxiosInstance = apiClient,
): Promise<CameraDetail> {
  const response = await client.post<CameraDetail>("/cameras", request);
  return response.data;
}

export async function getCamera(
  cameraId: string,
  client: AxiosInstance = apiClient,
): Promise<CameraDetail> {
  const response = await client.get<CameraDetail>(
    `/cameras/${encodeURIComponent(cameraId)}`,
  );
  return response.data;
}

export async function updateCamera(
  cameraId: string,
  request: CameraUpdateRequest,
  client: AxiosInstance = apiClient,
): Promise<CameraDetail> {
  const response = await client.put<CameraDetail>(
    `/cameras/${encodeURIComponent(cameraId)}`,
    request,
  );
  return response.data;
}

export async function setDefaultPreviewSource(
  cameraId: string,
  request: SetDefaultPreviewSourceRequest,
  client: AxiosInstance = apiClient,
): Promise<DefaultPreviewSourceResponse> {
  const response = await client.patch<DefaultPreviewSourceResponse>(
    `/cameras/${encodeURIComponent(cameraId)}/default-preview-source`,
    request,
  );
  return response.data;
}

export async function deleteCamera(
  cameraId: string,
  client: AxiosInstance = apiClient,
) {
  await client.delete(`/cameras/${encodeURIComponent(cameraId)}`);
}

export async function prepareCameraSourcePlayback(
  sourceId: string,
  client: AxiosInstance = apiClient,
): Promise<PlaybackInfo> {
  const response = await client.post<PlaybackInfo>(
    `/camera-sources/${encodeURIComponent(sourceId)}/playback`,
  );
  return response.data;
}
