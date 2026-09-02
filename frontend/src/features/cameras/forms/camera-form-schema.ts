import { z } from "zod";

/** 创建和编辑共用的可变连接字段规则；DTO 形状仍由各自表单模块单独定义。 */
export const cameraConnectionFormShape = {
  name: z
    .string()
    .trim()
    .min(1, "摄像头名称不能为空。")
    .max(128, "摄像头名称不能超过 128 个字符。"),
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
} as const;

/** Source 的公共可编辑字段；编辑表单会在此基础上额外接受稳定 `source_id`。 */
export const cameraSourceFormShape = {
  name: z
    .string()
    .trim()
    .min(1, "视频源名称不能为空。")
    .max(128, "视频源名称不能超过 128 个字符。"),
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
} as const;

type ValidatedCameraSource = {
  url_suffix: string;
  is_default_preview: boolean;
};

/**
 * 创建和完整编辑都必须即时检查唯一默认源与规范化后缀重复。
 *
 * Backend 仍是最终规则；这里共享纯校验，避免两个表单在同一业务字段上给出不同结果。
 */
export function validateCameraSourceCollection(
  value: { sources: ValidatedCameraSource[] },
  context: z.RefinementCtx,
) {
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
}
