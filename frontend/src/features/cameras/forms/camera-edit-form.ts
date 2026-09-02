import { z } from "zod";

import type {
  CameraDetail,
  CameraUpdateRequest,
} from "@/features/cameras/api/cameras-api";
import {
  cameraConnectionFormShape,
  cameraSourceFormShape,
  validateCameraSourceCollection,
} from "@/features/cameras/forms/camera-form-schema";

const cameraEditSourceSchema = z.strictObject({
  // 既有行携带 Backend ID；新增行保持 undefined。该值不由用户编辑，Backend 仍会验证所有权。
  source_id: z.string().optional(),
  ...cameraSourceFormShape,
});

export const cameraEditFormSchema = z
  .strictObject({
    ...cameraConnectionFormShape,
    sources: z.array(cameraEditSourceSchema).min(1, "至少需要一路视频源。"),
  })
  .superRefine(validateCameraSourceCollection);

export type CameraEditFormValues = z.input<typeof cameraEditFormSchema>;
export type ValidatedCameraEditFormValues = z.output<
  typeof cameraEditFormSchema
>;

/** 每次打开 Dialog 时从页面当前显示的详情生成一份独立草稿。 */
export function toCameraEditFormValues(
  camera: CameraDetail,
): CameraEditFormValues {
  return {
    name: camera.name,
    ip_address: camera.ip_address,
    rtsp_port: camera.rtsp_port,
    username: camera.username,
    password: camera.password,
    sources: camera.sources.map((source) => ({
      source_id: source.source_id,
      name: source.name,
      url_suffix: source.url_suffix,
      is_default_preview: source.is_default_preview,
    })),
  };
}

export function createEmptyCameraEditSource(isDefaultPreview = false) {
  return {
    name: "",
    url_suffix: "",
    is_default_preview: isDefaultPreview,
  } satisfies CameraEditFormValues["sources"][number];
}

/**
 * 只把 Update 契约允许的字段发送给 Backend。
 *
 * `useFieldArray` 的 UI key 不在表单值中；新增 Source 也不会发送空 ID 或 null。
 */
export function toCameraUpdateRequest(
  values: ValidatedCameraEditFormValues,
): CameraUpdateRequest {
  return {
    name: values.name,
    ip_address: values.ip_address,
    rtsp_port: values.rtsp_port,
    username: values.username,
    password: values.password,
    sources: values.sources.map((source) => ({
      ...(source.source_id === undefined
        ? {}
        : { source_id: source.source_id }),
      name: source.name,
      url_suffix: source.url_suffix,
      is_default_preview: source.is_default_preview,
    })),
  };
}
