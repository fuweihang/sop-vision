import { z } from "zod";

import type { CameraCreateRequest } from "@/features/cameras/api/cameras-api";

const requiredTrimmedString = (label: string, maxLength: number) =>
  z
    .string()
    .trim()
    .min(1, `${label}不能为空。`)
    .max(maxLength, `${label}不能超过 ${maxLength} 个字符。`);

const cameraSourceSchema = z.strictObject({
  name: requiredTrimmedString("视频源名称", 128),
  url_suffix: z
    .string()
    .trim()
    // Backend 会执行同样的规范化。Frontend 提前处理是为了准确发现“/a”和“a”的重复，
    // 但不会改写输入框中的草稿；只有最终发送的请求使用规范化结果。
    .transform((value) => value.replace(/^\/+/, ""))
    .pipe(
      z
        .string()
        .min(1, "URL 后缀不能为空。")
        .max(1024, "URL 后缀不能超过 1024 个字符。"),
    ),
  is_default_preview: z.boolean(),
});

export const cameraCreateFormSchema = z
  .strictObject({
    name: requiredTrimmedString("摄像头名称", 128),
    ip_address: z.ipv4({ error: "请输入有效的 IPv4 地址。" }),
    rtsp_port: z
      .number({ error: "请输入有效的 RTSP 端口。" })
      .int("RTSP 端口必须是整数。")
      .min(1, "RTSP 端口必须在 1 到 65535 之间。")
      .max(65535, "RTSP 端口必须在 1 到 65535 之间。"),
    // 凭据不能 trim。空格可能是设备真实凭据的一部分，擅自修改会保存一份无法连接的配置。
    username: z
      .string()
      .min(1, "用户名不能为空。")
      .max(128, "用户名不能超过 128 个字符。"),
    password: z
      .string()
      .min(1, "密码不能为空。")
      .max(512, "密码不能超过 512 个字符。"),
    sources: z.array(cameraSourceSchema).min(1, "至少需要一路视频源。"),
  })
  .superRefine((value, context) => {
    const defaultIndexes = value.sources.flatMap((source, index) =>
      source.is_default_preview ? [index] : [],
    );

    if (defaultIndexes.length === 0) {
      context.addIssue({
        code: "custom",
        path: ["sources"],
        message: "请选择一路默认预览源。",
      });
    } else if (defaultIndexes.length > 1) {
      for (const index of defaultIndexes.slice(1)) {
        context.addIssue({
          code: "custom",
          path: ["sources", index, "is_default_preview"],
          message: "只能选择一路默认预览源。",
        });
      }
    }

    const suffixIndexes = new Map<string, number>();
    value.sources.forEach((source, index) => {
      const firstIndex = suffixIndexes.get(source.url_suffix);
      if (firstIndex === undefined) {
        suffixIndexes.set(source.url_suffix, index);
        return;
      }

      context.addIssue({
        code: "custom",
        path: ["sources", index, "url_suffix"],
        message: `URL 后缀不能与第 ${firstIndex + 1} 路视频源重复。`,
      });
    });
  });

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
