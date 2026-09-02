import type { ProblemDetails } from "@/lib/api-errors";
import {
  ApiProblemError,
  ApiTransportError,
  ApiUnexpectedResponseError,
} from "@/lib/api-errors";

/**
 * Camera 的 PUT 和默认源 PATCH 共享同一组“提交是否确定失败”规则。
 *
 * 这里故意只返回四个业务分类，不包含提示文本、表单字段或 Query 操作。这样两个写入口不会因为
 * 各自的 UI 实现逐渐产生不同的 404/422/500 判断，同时也不会形成通用 Mutation 框架。
 */
export type CameraWriteFailureClassification =
  | { readonly kind: "camera-not-found" }
  | { readonly kind: "validation"; readonly problem: ProblemDetails }
  | { readonly kind: "aggregate-invalid" }
  | { readonly kind: "unknown" };

export function classifyCameraWriteFailure(
  error: unknown,
): CameraWriteFailureClassification {
  if (
    error instanceof ApiTransportError ||
    error instanceof ApiUnexpectedResponseError
  ) {
    return { kind: "unknown" };
  }

  if (
    error instanceof ApiProblemError &&
    error.problem.status === 422 &&
    error.problem.code === "VALIDATION_ERROR"
  ) {
    return { kind: "validation", problem: error.problem };
  }

  if (
    error instanceof ApiProblemError &&
    error.problem.status === 404 &&
    error.problem.code === "CAMERA_NOT_FOUND"
  ) {
    return { kind: "camera-not-found" };
  }

  if (
    error instanceof ApiProblemError &&
    error.problem.status === 500 &&
    error.problem.code === "CAMERA_AGGREGATE_INVALID"
  ) {
    return { kind: "aggregate-invalid" };
  }

  if (error instanceof ApiProblemError) {
    // 契约外的可信 Problem 也不能证明写入未提交，必须按结果未知处理。
    return { kind: "unknown" };
  }

  // 普通 Error 通常是程序缺陷。保留原异常和堆栈，不能伪装成可恢复的业务提示。
  throw error;
}
