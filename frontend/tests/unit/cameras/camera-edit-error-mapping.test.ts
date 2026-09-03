import { expect, test } from "vitest";

import { mapCameraEditFailure } from "@/features/cameras/forms/camera-edit-error-mapping";
import {
  ApiProblemError,
  ApiTransportError,
  ApiUnexpectedResponseError,
} from "@/lib/api-errors";
import { buildProblem } from "@/mocks/cameras/fixtures";

function problemError(
  status: number,
  code: string,
  errors: Parameters<typeof buildProblem>[0]["errors"] = [],
) {
  return new ApiProblemError(
    buildProblem({
      status,
      code,
      instance: "/api/v1/cameras/camera-id",
      errors,
    }),
  );
}

test("422 映射可见字段并把允许的 source_id 错误留在对应行", () => {
  const failure = mapCameraEditFailure(
    problemError(422, "VALIDATION_ERROR", [
      {
        field: "sources[1].source_id",
        code: "SOURCE_NOT_OWNED_BY_CAMERA",
        detail: "该视频源不属于当前摄像头。",
      },
      {
        field: "sources[0].name",
        code: "REQUIRED",
        detail: "该字段为必填项。",
      },
    ]),
    2,
  );

  expect(failure).toEqual({
    kind: "validation",
    fieldErrors: [
      {
        fieldName: "sources.1.source_id",
        message: "该视频源不属于当前摄像头。",
        focusable: false,
      },
      {
        fieldName: "sources.0.name",
        message: "该字段为必填项。",
        focusable: true,
      },
    ],
    formAlert: undefined,
  });
});

test("越界路径和 source_id 未知错误码进入表单级 Alert", () => {
  const failure = mapCameraEditFailure(
    problemError(422, "VALIDATION_ERROR", [
      {
        field: "sources[99].name",
        code: "REQUIRED",
        detail: "无法定位的字段。",
      },
      {
        field: "sources[0].source_id",
        code: "UNEXPECTED_SOURCE_ERROR",
        detail: "无法安全映射的 ID 错误。",
      },
    ]),
    2,
  );

  expect(failure.kind).toBe("validation");
  if (failure.kind !== "validation") {
    return;
  }
  expect(failure.fieldErrors).toEqual([]);
  expect(failure.formAlert?.messages).toEqual([
    "无法定位的字段。",
    "无法安全映射的 ID 错误。",
  ]);
});

test.each([
  new ApiTransportError(),
  new ApiUnexpectedResponseError(500),
  problemError(503, "DATABASE_UNAVAILABLE"),
  problemError(500, "INTERNAL_SERVER_ERROR"),
  problemError(409, "UNEXPECTED_CONFLICT"),
])("%s 属于更新结果未知", (error) => {
  expect(mapCameraEditFailure(error, 2)).toMatchObject({
    kind: "alert",
    formAlert: { kind: "unknown", title: "更新结果未知" },
  });
});

test("404 Camera 不存在和损坏聚合是确定失败", () => {
  expect(
    mapCameraEditFailure(problemError(404, "CAMERA_NOT_FOUND"), 2),
  ).toMatchObject({
    kind: "alert",
    formAlert: { kind: "error", title: "未能更新摄像头" },
  });
  expect(
    mapCameraEditFailure(problemError(500, "CAMERA_AGGREGATE_INVALID"), 2),
  ).toMatchObject({
    kind: "alert",
    formAlert: { kind: "error", title: "未能更新摄像头" },
  });
});
