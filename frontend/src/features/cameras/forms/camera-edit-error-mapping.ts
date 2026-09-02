import type { FieldPath } from "react-hook-form";

import type { CameraEditFormValues } from "@/features/cameras/forms/camera-edit-form";
import {
  ApiProblemError,
  ApiTransportError,
  ApiUnexpectedResponseError,
  mapProblemFieldErrors,
  type ParsedProblemFieldPath,
  type ProblemFieldError,
} from "@/lib/api-errors";

export type CameraEditFieldName = FieldPath<CameraEditFormValues>;

export interface CameraEditFormAlert {
  readonly kind: "error" | "unknown";
  readonly title: string;
  readonly messages: readonly string[];
}

export interface CameraEditFieldError {
  readonly fieldName: CameraEditFieldName;
  readonly message: string;
  readonly focusable: boolean;
}

export type CameraEditFailure =
  | {
      readonly kind: "validation";
      readonly fieldErrors: readonly CameraEditFieldError[];
      readonly formAlert: CameraEditFormAlert | undefined;
    }
  | {
      readonly kind: "alert";
      readonly formAlert: CameraEditFormAlert;
    };

const TOP_LEVEL_FIELDS = new Set([
  "name",
  "ip_address",
  "rtsp_port",
  "username",
  "password",
]);
const VISIBLE_SOURCE_FIELDS = new Set([
  "name",
  "url_suffix",
  "is_default_preview",
]);
const SOURCE_ID_ERROR_CODES = new Set([
  "INVALID_UUID",
  "SOURCE_NOT_OWNED_BY_CAMERA",
  "DUPLICATE_SOURCE_ID",
]);

function mappedField(
  path: ParsedProblemFieldPath,
  error: ProblemFieldError,
  sourceCount: number,
): { fieldName: CameraEditFieldName; focusable: boolean } | undefined {
  if (
    path.length === 1 &&
    typeof path[0] === "string" &&
    TOP_LEVEL_FIELDS.has(path[0])
  ) {
    return { fieldName: path[0] as CameraEditFieldName, focusable: true };
  }

  const [root, index, field] = path;
  if (
    path.length !== 3 ||
    root !== "sources" ||
    typeof index !== "number" ||
    index >= sourceCount ||
    typeof field !== "string"
  ) {
    return undefined;
  }

  if (VISIBLE_SOURCE_FIELDS.has(field)) {
    return {
      fieldName: `sources.${index}.${field}` as CameraEditFieldName,
      focusable: true,
    };
  }

  if (field === "source_id" && SOURCE_ID_ERROR_CODES.has(error.code)) {
    return {
      fieldName: `sources.${index}.source_id`,
      focusable: false,
    };
  }
  return undefined;
}

function problemAlert(
  title: string,
  messages: readonly string[],
): CameraEditFormAlert {
  return {
    kind: "error",
    title,
    messages:
      messages.length === 0
        ? ["请检查表单后重试；如问题持续，请联系管理员。"]
        : messages,
  };
}

function unknownResultAlert(): CameraEditFormAlert {
  return {
    kind: "unknown",
    title: "更新结果未知",
    messages: [
      "服务端可能已经保存了上一请求。页面数据正在重新读取，当前编辑草稿不会被覆盖。",
      "再次保存会发送一条新的完整更新，并需要再次确认。",
    ],
  };
}

/** 把脱敏 API 错误转换为编辑表单可安全消费的固定状态。 */
export function mapCameraEditFailure(
  error: unknown,
  sourceCount: number,
): CameraEditFailure {
  if (
    error instanceof ApiTransportError ||
    error instanceof ApiUnexpectedResponseError
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
    const fieldErrors: CameraEditFieldError[] = [];

    for (const mapped of mapping.fields) {
      const field = mappedField(mapped.path, mapped.error, sourceCount);
      if (field === undefined) {
        formMessages.push(mapped.error.detail);
      } else {
        fieldErrors.push({ ...field, message: mapped.error.detail });
      }
    }

    return {
      kind: "validation",
      fieldErrors,
      formAlert:
        formMessages.length === 0
          ? undefined
          : problemAlert("未能更新摄像头", formMessages),
    };
  }

  if (
    error instanceof ApiProblemError &&
    error.problem.status === 404 &&
    error.problem.code === "CAMERA_NOT_FOUND"
  ) {
    return {
      kind: "alert",
      formAlert: problemAlert("未能更新摄像头", ["该摄像头不存在或已被删除。"]),
    };
  }

  if (
    error instanceof ApiProblemError &&
    error.problem.status === 500 &&
    error.problem.code === "CAMERA_AGGREGATE_INVALID"
  ) {
    return {
      kind: "alert",
      formAlert: problemAlert("未能更新摄像头", [
        "当前摄像头配置无效，请联系管理员检查服务端数据。",
      ]),
    };
  }

  if (error instanceof ApiProblemError) {
    // 除三类确定失败外，可信 Problem 也不能证明数据库没有提交；未知 4xx 同样属于操作契约之外。
    return { kind: "alert", formAlert: unknownResultAlert() };
  }

  throw error;
}
