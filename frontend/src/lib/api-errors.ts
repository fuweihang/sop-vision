import axios, { AxiosHeaders, type AxiosResponse } from "axios";
import { z } from "zod";

import type { components } from "@/generated/openapi";

const PROBLEM_MEDIA_TYPE = "application/problem+json";

/** OpenAPI 生成类型是编译期契约；此别名不创建第二份手写 DTO。 */
export type ProblemDetails = components["schemas"]["ProblemDetails"];
export type ProblemFieldError = components["schemas"]["FieldError"];

// Problem.context 允许任意 JSON 值，但绝不允许函数、undefined 或循环对象。Zod 4 的 z.json()
// 与后端 JsonValue Schema 同义，避免在前端维护一份容易漂移的递归联合类型。
const problemSchema: z.ZodType<ProblemDetails> = z.strictObject({
  type: z.string(),
  title: z.string(),
  status: z.number().int().min(400).max(599),
  code: z.string(),
  detail: z.string(),
  instance: z.string(),
  trace_id: z.string(),
  errors: z
    .array(
      z.strictObject({
        field: z.string(),
        code: z.string(),
        detail: z.string(),
      }),
    )
    .default([]),
  context: z.record(z.string(), z.json()).default({}),
});

/**
 * 后端明确返回且通过运行时验证的业务 Problem。
 *
 * message 故意使用固定文本：调用方可以按 problem.status/code/errors/context 分支，但默认
 * Error 序列化不会复制可能随服务端变化的 title/detail，更不会携带 Axios 原始响应。
 */
export class ApiProblemError extends Error {
  override readonly name = "ApiProblemError";
  readonly problem: ProblemDetails;

  constructor(problem: ProblemDetails) {
    super("API 返回了结构化业务错误。");
    this.problem = problem;
  }
}

/** 请求已发出但没有收到可判断的 HTTP 响应；它没有业务 code。 */
export class ApiTransportError extends Error {
  override readonly name = "ApiTransportError";
  readonly kind = "transport";

  constructor() {
    super("网络请求未收到有效响应。");
  }
}

/** 服务端有响应，但它不满足公共 Problem 契约；它同样没有业务 code。 */
export class ApiUnexpectedResponseError extends Error {
  override readonly name = "ApiUnexpectedResponseError";
  readonly kind = "unexpected-response";
  readonly status: number;
  readonly traceId: string | undefined;

  constructor(status: number, traceId?: string) {
    super("服务端返回了无法识别的错误响应。");
    this.status = status;
    this.traceId = traceId;
  }
}

function readHeader(
  headers: AxiosResponse["headers"],
  name: string,
): string | undefined {
  // 浏览器适配器返回 AxiosHeaders，部分测试适配器会返回普通对象；后者按大小写无关方式查找。
  const value =
    headers instanceof AxiosHeaders
      ? headers.get(name)
      : Object.entries(headers).find(
          ([headerName]) => headerName.toLowerCase() === name.toLowerCase(),
        )?.[1];
  return typeof value === "string" ? value : undefined;
}

function isProblemMediaType(contentType: string | undefined) {
  return (
    contentType?.split(";", 1)[0]?.trim().toLowerCase() === PROBLEM_MEDIA_TYPE
  );
}

/**
 * 把未知异常收敛为可安全传播的前端错误。
 *
 * 只有媒体类型、Schema、HTTP status 和 X-Trace-Id 全部一致时，响应才是可信 Problem。
 * FastAPI 占位 handler 当前产生的临时 500 不满足该条件，因此不会形成 Foundation 之外的
 * 特殊业务分支。非 Axios 异常通常表示编程错误，保持原样抛出以保留真实堆栈。
 */
export function mapApiError(error: unknown): unknown {
  if (!axios.isAxiosError(error)) {
    return error;
  }

  const response = error.response;
  if (response === undefined) {
    return new ApiTransportError();
  }

  const contentType = readHeader(response.headers, "content-type");
  const traceId = readHeader(response.headers, "x-trace-id");
  const parsed = isProblemMediaType(contentType)
    ? problemSchema.safeParse(response.data)
    : undefined;

  if (
    parsed?.success === true &&
    parsed.data.status === response.status &&
    traceId !== undefined &&
    parsed.data.trace_id === traceId
  ) {
    return new ApiProblemError(parsed.data);
  }

  return new ApiUnexpectedResponseError(response.status, traceId);
}

export type ParsedProblemFieldPath = readonly (string | number)[];

export interface MappedProblemFieldError {
  readonly path: ParsedProblemFieldPath;
  readonly error: ProblemFieldError;
}

export interface ProblemFieldErrorMapping {
  readonly fields: readonly MappedProblemFieldError[];
  readonly form: readonly ProblemFieldError[];
}

// 字段名使用 snake_case 标识符，数组下标必须是非负十进制整数。拒绝空段、负数、引号和
// prototype 风格的任意属性访问，防止后续表单代码把不可信路径当成对象写入指令。
const FIELD_PATH_PATTERN =
  /^[A-Za-z_][A-Za-z0-9_]*(?:\[\d+\]|\.[A-Za-z_][A-Za-z0-9_]*)*$/;
const FIELD_PATH_TOKEN_PATTERN = /([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]/g;

/** 将 `sources[1].name` 解析为 `['sources', 1, 'name']`，不猜测畸形路径。 */
export function parseProblemFieldPath(
  field: string,
): ParsedProblemFieldPath | undefined {
  if (!FIELD_PATH_PATTERN.test(field)) {
    return undefined;
  }

  const path: (string | number)[] = [];
  for (const match of field.matchAll(FIELD_PATH_TOKEN_PATTERN)) {
    if (match[2] !== undefined) {
      const index = Number(match[2]);
      if (!Number.isSafeInteger(index)) {
        return undefined;
      }
      path.push(index);
    } else if (match[1] !== undefined) {
      path.push(match[1]);
    }
  }
  return path;
}

/** 把可定位错误与表单级错误分开，且保持后端原始顺序。 */
export function mapProblemFieldErrors(
  problem: ProblemDetails,
): ProblemFieldErrorMapping {
  const fields: MappedProblemFieldError[] = [];
  const form: ProblemFieldError[] = [];

  for (const error of problem.errors ?? []) {
    const path = parseProblemFieldPath(error.field);
    if (path === undefined) {
      form.push(error);
    } else {
      fields.push({ path, error });
    }
  }

  return { fields, form };
}
