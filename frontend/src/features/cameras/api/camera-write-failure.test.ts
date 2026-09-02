import { expect, test } from "vitest";

import { classifyCameraWriteFailure } from "@/features/cameras/api/camera-write-failure";
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
      instance: "/api/v1/cameras/camera-id",
    }),
  );
}

test.each([
  [problemError(404, "CAMERA_NOT_FOUND"), "camera-not-found"],
  [problemError(422, "VALIDATION_ERROR"), "validation"],
  [problemError(500, "CAMERA_AGGREGATE_INVALID"), "aggregate-invalid"],
] as const)("把确定失败 %s 分类为 %s", (error, kind) => {
  expect(classifyCameraWriteFailure(error)).toMatchObject({ kind });
});

test.each([
  new ApiTransportError(),
  new ApiUnexpectedResponseError(502),
  problemError(503, "DATABASE_UNAVAILABLE"),
  problemError(500, "INTERNAL_SERVER_ERROR"),
  problemError(409, "UNEXPECTED_CONFLICT"),
])("把无法确认提交结果的 %s 分类为 unknown", (error) => {
  expect(classifyCameraWriteFailure(error)).toEqual({ kind: "unknown" });
});

test("程序错误保持原样抛出", () => {
  const error = new Error("测试程序错误");
  expect(() => classifyCameraWriteFailure(error)).toThrow(error);
});
