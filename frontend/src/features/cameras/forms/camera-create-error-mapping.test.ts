import { describe, expect, test } from "vitest";

import {
  fieldErrorMessage,
  mapCameraCreateFailure,
} from "@/features/cameras/forms/camera-create-error-mapping";
import {
  ApiProblemError,
  ApiTransportError,
  ApiUnexpectedResponseError,
  type ProblemDetails,
} from "@/lib/api-errors";

function buildProblem(overrides: Partial<ProblemDetails> = {}): ProblemDetails {
  return {
    type: "urn:sop-vision:problem:validation-error",
    title: "请求字段验证失败",
    status: 422,
    code: "VALIDATION_ERROR",
    detail: "存在无效字段。",
    instance: "/api/v1/cameras",
    trace_id: "tr_camera_create_error_mapping",
    errors: [],
    context: {},
    ...overrides,
  };
}

describe("Camera 创建错误映射", () => {
  test("把当前草稿中的字段错误映射到表单，其余错误保留在 Alert", () => {
    const failure = mapCameraCreateFailure(
      new ApiProblemError(
        buildProblem({
          errors: [
            {
              field: "sources[-1].name",
              code: "INVALID_FIELD_PATH",
              detail: "字段路径无效。",
            },
            {
              field: "name",
              code: "REQUIRED",
              detail: "Camera 名称不能为空。",
            },
            {
              field: "sources[1].url_suffix",
              code: "DUPLICATE_SOURCE_SUFFIX",
              detail: "URL 后缀重复。",
            },
            {
              field: "sources[2].name",
              code: "REQUIRED",
              detail: "第三路 Source 已不在当前草稿中。",
            },
          ],
        }),
      ),
      2,
    );

    expect(failure).toEqual({
      kind: "validation",
      fieldErrors: [
        { fieldName: "name", message: "Camera 名称不能为空。" },
        {
          fieldName: "sources.1.url_suffix",
          message: "URL 后缀重复。",
        },
      ],
      formAlert: {
        kind: "error",
        title: "未能创建摄像头",
        messages: ["字段路径无效。", "第三路 Source 已不在当前草稿中。"],
      },
    });
  });

  test.each([
    new ApiTransportError(),
    new ApiUnexpectedResponseError(502),
    new ApiProblemError(
      buildProblem({ status: 503, code: "DATABASE_UNAVAILABLE" }),
    ),
  ])("把无法确认提交结果的错误映射为持久风险提示", (error) => {
    expect(mapCameraCreateFailure(error, 1)).toEqual({
      kind: "alert",
      formAlert: {
        kind: "unknown",
        title: "创建结果未知",
        messages: [
          "服务端可能已经创建成功。再次保存会发送一条新的创建请求，并可能产生重复摄像头。",
        ],
      },
    });
  });

  test("把其他可信 Problem 映射为不包含服务端 detail 的确定失败", () => {
    expect(
      mapCameraCreateFailure(
        new ApiProblemError(
          buildProblem({
            status: 409,
            code: "CAMERA_CONFLICT",
            detail: "不应直接展示的服务端文本。",
          }),
        ),
        1,
      ),
    ).toEqual({
      kind: "alert",
      formAlert: {
        kind: "error",
        title: "未能创建摄像头",
        messages: ["服务端拒绝了本次请求（409/CAMERA_CONFLICT）。"],
      },
    });
  });

  test("非 API 编程错误保持原异常抛出", () => {
    const error = new TypeError("程序错误");
    expect(() => mapCameraCreateFailure(error, 1)).toThrow(error);
  });

  test("字段组件只显示字符串错误消息", () => {
    expect(fieldErrorMessage("字段错误")).toBe("字段错误");
    expect(fieldErrorMessage({ message: "不得隐式转为文本" })).toBeUndefined();
  });
});
