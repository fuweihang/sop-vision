import type { FieldPath } from "react-hook-form";

import type { CameraCreateFormValues } from "@/features/cameras/forms/camera-create-form";
import {
  ApiProblemError,
  ApiTransportError,
  ApiUnexpectedResponseError,
  mapProblemFieldErrors,
  type ParsedProblemFieldPath,
} from "@/lib/api-errors";

export type CameraCreateFieldName = FieldPath<CameraCreateFormValues>;

export interface CameraCreateFormAlert {
  readonly kind: "error" | "unknown";
  readonly title: string;
  readonly messages: readonly string[];
}

export interface CameraCreateFieldError {
  readonly fieldName: CameraCreateFieldName;
  readonly message: string;
}

export type CameraCreateFailure =
  | {
      readonly kind: "validation";
      readonly fieldErrors: readonly CameraCreateFieldError[];
      readonly formAlert: CameraCreateFormAlert | undefined;
    }
  | {
      readonly kind: "alert";
      readonly formAlert: CameraCreateFormAlert;
    };

const TOP_LEVEL_FIELDS = new Set([
  "name",
  "ip_address",
  "rtsp_port",
  "username",
  "password",
]);
const SOURCE_FIELDS = new Set(["name", "url_suffix", "is_default_preview"]);

/**
 * 只允许 Backend 当前公开的创建字段进入 React Hook Form。
 *
 * Source 下标还必须落在当前草稿范围内；服务端若返回过期或未知路径，错误只能进入表单级 Alert，
 * 不能让不可信路径驱动对象写入或聚焦不存在的控件。
 */
function mappedFieldName(
  path: ParsedProblemFieldPath,
  sourceCount: number,
): CameraCreateFieldName | undefined {
  if (
    path.length === 1 &&
    typeof path[0] === "string" &&
    TOP_LEVEL_FIELDS.has(path[0])
  ) {
    return path[0] as CameraCreateFieldName;
  }

  const [root, index, field] = path;
  if (
    path.length === 3 &&
    root === "sources" &&
    typeof index === "number" &&
    index < sourceCount &&
    typeof field === "string" &&
    SOURCE_FIELDS.has(field)
  ) {
    return `sources.${index}.${field}` as CameraCreateFieldName;
  }
  return undefined;
}

function problemAlert(messages: readonly string[]): CameraCreateFormAlert {
  return {
    kind: "error",
    title: "未能创建摄像头",
    messages:
      messages.length === 0
        ? ["请检查表单后重试；如问题持续，请联系管理员。"]
        : messages,
  };
}

function unknownResultAlert(): CameraCreateFormAlert {
  return {
    kind: "unknown",
    title: "创建结果未知",
    messages: [
      "服务端可能已经创建成功。再次保存会发送一条新的创建请求，并可能产生重复摄像头。",
    ],
  };
}

/** React Hook Form 的错误消息类型较宽；UI 只显示经过验证的文本。 */
export function fieldErrorMessage(message: unknown) {
  return typeof message === "string" ? message : undefined;
}

/**
 * 把已经脱敏的 API 错误转换为创建表单可以安全消费的结果。
 *
 * 函数不接触 DOM、React Hook Form 或 Mutation Cache，因此字段映射和“结果未知”判断可以独立测试。
 * 非 API 错误保持原异常抛出，避免把程序错误伪装成用户可以修正的业务失败。
 */
export function mapCameraCreateFailure(
  error: unknown,
  sourceCount: number,
): CameraCreateFailure {
  if (
    error instanceof ApiTransportError ||
    error instanceof ApiUnexpectedResponseError ||
    (error instanceof ApiProblemError && error.problem.status === 503)
  ) {
    return { kind: "alert", formAlert: unknownResultAlert() };
  }

  if (
    error instanceof ApiProblemError &&
    error.problem.status === 422 &&
    error.problem.code === "VALIDATION_ERROR"
  ) {
    const mapping = mapProblemFieldErrors(error.problem);
    const formMessages = mapping.form.map((item) => item.detail);
    const fieldErrors: CameraCreateFieldError[] = [];

    for (const mapped of mapping.fields) {
      const fieldName = mappedFieldName(mapped.path, sourceCount);
      if (fieldName === undefined) {
        formMessages.push(mapped.error.detail);
      } else {
        fieldErrors.push({ fieldName, message: mapped.error.detail });
      }
    }

    return {
      kind: "validation",
      fieldErrors,
      formAlert:
        formMessages.length === 0 ? undefined : problemAlert(formMessages),
    };
  }

  if (error instanceof ApiProblemError) {
    return {
      kind: "alert",
      formAlert: problemAlert([
        `服务端拒绝了本次请求（${error.problem.status}/${error.problem.code}）。`,
      ]),
    };
  }

  throw error;
}
