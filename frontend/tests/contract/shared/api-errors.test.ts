import { describe, expect, test } from "vitest";

import {
  ApiProblemError,
  ApiTransportError,
  ApiUnexpectedResponseError,
  mapApiError,
  type ProblemDetails,
} from "@/lib/api-errors";

const TRACE_ID = "tr_frontend_test";
const SENSITIVE_VALUE = "shared-contract-secret-must-not-leak";

function buildProblem(overrides: Partial<ProblemDetails> = {}): ProblemDetails {
  return {
    type: "urn:sop-vision:problem:validation-error",
    title: "请求字段验证失败",
    status: 422,
    code: "VALIDATION_ERROR",
    detail: "存在无效字段。",
    instance: "/api/v1/cameras",
    trace_id: TRACE_ID,
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

function buildAxiosErrorResponse(
  data: unknown,
  options: {
    status?: number;
    contentType?: string;
    traceId?: string;
    includeTraceId?: boolean;
  } = {},
) {
  const headers: Record<string, string> = {
    "content-type":
      options.contentType ?? "application/problem+json; charset=utf-8",
  };
  if (options.includeTraceId !== false) {
    headers["x-trace-id"] = options.traceId ?? TRACE_ID;
  }
  return {
    isAxiosError: true,
    config: { data: "不得传播的请求体" },
    response: {
      data,
      status: options.status ?? 422,
      headers,
    },
  };
}

describe("API 错误映射", () => {
  test("只把媒体类型、Schema、状态和 trace 一致的响应识别为 Problem", () => {
    const mapped = mapApiError(buildAxiosErrorResponse(buildProblem()));

    expect(mapped).toBeInstanceOf(ApiProblemError);
    expect(mapped).toMatchObject({
      problem: {
        status: 422,
        code: "VALIDATION_ERROR",
        trace_id: TRACE_ID,
      },
    });
  });

  test.each([
    ["错误媒体类型", { contentType: "application/json" }, buildProblem()],
    ["HTTP 状态不一致", { status: 503 }, buildProblem()],
    ["trace 不一致", { traceId: "tr_other" }, buildProblem()],
    ["缺少 trace 响应头", { includeTraceId: false }, buildProblem()],
    ["Problem 含未知字段", {}, { ...buildProblem(), raw_input: "secret" }],
  ])("%s 时返回不带业务 code 的非预期响应错误", (_name, options, body) => {
    const mapped = mapApiError(buildAxiosErrorResponse(body, options));

    expect(mapped).toBeInstanceOf(ApiUnexpectedResponseError);
    expect(mapped).not.toHaveProperty("code");
    expect(mapped).not.toHaveProperty("response");
  });

  test("无 HTTP 响应时不保留 Axios 请求配置或伪造业务 code", () => {
    const mapped = mapApiError({
      isAxiosError: true,
      config: { data: `password=${SENSITIVE_VALUE}` },
      request: {},
    });

    expect(mapped).toBeInstanceOf(ApiTransportError);
    expect(mapped).not.toHaveProperty("code");
    expect(JSON.stringify(mapped)).not.toContain(SENSITIVE_VALUE);
  });

  test("非 Axios 编程错误保持原样", () => {
    const original = new TypeError("程序错误");
    expect(mapApiError(original)).toBe(original);
  });
});
