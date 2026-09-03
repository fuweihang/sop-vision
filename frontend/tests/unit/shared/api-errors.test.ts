import { describe, expect, test } from "vitest";

import {
  mapProblemFieldErrors,
  parseProblemFieldPath,
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
    trace_id: "tr_frontend_test",
    errors: [
      {
        field: "sources[1].name",
        code: "REQUIRED",
        detail: "该字段为必填项。",
      },
    ],
    context: {},
    ...overrides,
  };
}

describe("Problem 字段路径映射", () => {
  test("动态 Source 下标映射为准确的结构化路径", () => {
    expect(parseProblemFieldPath("sources[1].name")).toEqual([
      "sources",
      1,
      "name",
    ]);
    expect(parseProblemFieldPath("sources[10].url_suffix")).toEqual([
      "sources",
      10,
      "url_suffix",
    ]);
  });

  test.each([
    "sources[-1].name",
    "sources[].name",
    "sources[1][name]",
    ".sources[1].name",
    "sources[999999999999999999999].name",
  ])("拒绝畸形或不安全路径 %s", (field) => {
    expect(parseProblemFieldPath(field)).toBeUndefined();
  });

  test("畸形字段进入表单级错误且保持后端顺序", () => {
    const problem = buildProblem({
      errors: [
        {
          field: "sources[1].name",
          code: "REQUIRED",
          detail: "第二路名称必填。",
        },
        {
          field: "sources[-1].name",
          code: "INVALID_FIELD_PATH",
          detail: "字段路径无效。",
        },
      ],
    });

    const mapped = mapProblemFieldErrors(problem);

    expect(mapped.fields).toEqual([
      {
        path: ["sources", 1, "name"],
        error: problem.errors?.[0],
      },
    ]);
    expect(mapped.form).toEqual([problem.errors?.[1]]);
  });
});
