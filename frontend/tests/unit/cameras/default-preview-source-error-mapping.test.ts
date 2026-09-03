import { expect, test } from "vitest";

import { mapDefaultPreviewSourceFailure } from "@/features/cameras/components/default-preview-source-error-mapping";
import {
  ApiProblemError,
  ApiTransportError,
  ApiUnexpectedResponseError,
} from "@/lib/api-errors";
import { buildProblem } from "@/mocks/cameras/fixtures";

function problemError(status: number, code: string) {
  return new ApiProblemError(
    buildProblem({
      status,
      code,
      instance: "/api/v1/cameras/camera-id/default-preview-source",
    }),
  );
}

test.each([
  [404, "CAMERA_NOT_FOUND", "该摄像头不存在或已被删除。"],
  [
    422,
    "VALIDATION_ERROR",
    "该视频源已不存在或不属于当前摄像头，请刷新后重试。",
  ],
  [
    500,
    "CAMERA_AGGREGATE_INVALID",
    "当前摄像头配置无效，请联系管理员检查服务端数据。",
  ],
] as const)("%i/%s 使用固定的确定失败提示", (status, code, message) => {
  expect(mapDefaultPreviewSourceFailure(problemError(status, code))).toEqual({
    kind: "error",
    title: "未能设置默认预览源",
    message,
  });
});

test.each([
  new ApiTransportError(),
  new ApiUnexpectedResponseError(500),
  problemError(503, "DATABASE_UNAVAILABLE"),
  problemError(500, "INTERNAL_SERVER_ERROR"),
])("%s 使用固定的结果未知提示", (error) => {
  expect(mapDefaultPreviewSourceFailure(error)).toMatchObject({
    kind: "unknown",
    title: "默认源设置结果未知",
  });
});
