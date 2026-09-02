import { z } from "zod";

import type { CameraCreateRequest } from "@/features/cameras/api/cameras-api";
import {
  cameraConnectionFormShape,
  cameraSourceFormShape,
  validateCameraSourceCollection,
} from "@/features/cameras/forms/camera-form-schema";

export const cameraCreateFormSchema = z
  .strictObject({
    ...cameraConnectionFormShape,
    sources: z
      .array(z.strictObject(cameraSourceFormShape))
      .min(1, "至少需要一路视频源。"),
  })
  .superRefine(validateCameraSourceCollection);

export type CameraCreateFormValues = z.input<typeof cameraCreateFormSchema>;
export type ValidatedCameraCreateFormValues = z.output<
  typeof cameraCreateFormSchema
>;

export const CAMERA_CREATE_DEFAULT_VALUES: CameraCreateFormValues = {
  name: "",
  ip_address: "",
  rtsp_port: 554,
  username: "",
  password: "",
  sources: [
    {
      name: "",
      url_suffix: "",
      is_default_preview: true,
    },
  ],
};

export function createEmptyCameraSource(isDefaultPreview = false) {
  return {
    name: "",
    url_suffix: "",
    is_default_preview: isDefaultPreview,
  } satisfies CameraCreateFormValues["sources"][number];
}

/**
 * 把 Zod 已验证和规范化的值收窄为 OpenAPI 请求类型。
 *
 * 单独保留这个边界可以让契约生成类型变化时在编译阶段失败，避免表单悄悄发送额外字段。
 */
export function toCameraCreateRequest(
  values: ValidatedCameraCreateFormValues,
): CameraCreateRequest {
  return values;
}
