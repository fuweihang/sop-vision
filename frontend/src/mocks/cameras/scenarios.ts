import {
  http,
  HttpResponse,
  type JsonBodyType,
  type RequestHandler,
} from "msw";

import { apiBaseUrl } from "@/lib/api-client";
import {
  buildCameraDetail,
  buildCameraPage,
  buildDefaultPreviewSourceResponse,
  buildProblem,
  CAMERA_FIXTURE_IDS,
  CAMERA_FIXTURE_TRACE_ID,
} from "@/mocks/cameras/fixtures";

export const CAMERAS_MSW_SCENARIO_NAMES = [
  "success",
  "empty-list",
  "search-no-results",
  "nested-validation-error",
  "camera-not-found",
  "dependency-unavailable",
  "initial-failure",
  "background-refresh-failure",
] as const;

export type CamerasMswScenarioName =
  (typeof CAMERAS_MSW_SCENARIO_NAMES)[number];

const scenarioNames = new Set<string>(CAMERAS_MSW_SCENARIO_NAMES);

export function isCamerasMswScenarioName(
  value: string,
): value is CamerasMswScenarioName {
  return scenarioNames.has(value);
}

const normalizedApiBaseUrl = apiBaseUrl.replace(/\/$/, "");
const camerasUrl = `${normalizedApiBaseUrl}/cameras`;
const cameraUrl = `${camerasUrl}/:cameraId`;
const defaultSourceUrl = `${cameraUrl}/default-preview-source`;

const successHeaders = {
  "X-Trace-Id": CAMERA_FIXTURE_TRACE_ID,
};

function jsonResponse<T extends JsonBodyType>(
  body: T,
  status = 200,
  headers: Record<string, string> = {},
) {
  return HttpResponse.json(body, {
    status,
    headers: { ...successHeaders, ...headers },
  });
}

function problemResponse(
  problem: ReturnType<typeof buildProblem>,
  headers: Record<string, string> = {},
) {
  /**
   * API Client 只信任同时满足 Problem JSON 媒体类型、响应 Trace Header，并且 body 中
   * `status` / `trace_id` 与 HTTP 响应一致的错误。这里统一生成完整响应，避免场景因漏掉
   * 任一约束而被 `mapApiError` 降级为 `ApiUnexpectedResponseError`，从而测试错了 UI 分支。
   */
  return HttpResponse.json(problem, {
    status: problem.status,
    headers: {
      ...successHeaders,
      "Content-Type": "application/problem+json",
      ...headers,
    },
  });
}

function unavailableProblem(instance: string) {
  return problemResponse(
    buildProblem({
      status: 503,
      code: "DATABASE_UNAVAILABLE",
      instance,
      title: "服务暂不可用",
    }),
  );
}

/**
 * 创建一个完全独立的 Cameras 场景。
 *
 * 计数器位于工厂闭包内，不能导出或共享；测试每次重新调用本函数即可得到确定的请求序列。
 * 返回六条目标 operation 的完整 handler，任何未声明请求都交给全局 `onUnhandledRequest=error`
 * 阻断，绝不会透传到真实 Backend 或 MediaMTX。
 */
export function createCamerasMswScenario(
  scenario: CamerasMswScenarioName,
): RequestHandler[] {
  let listRequestCount = 0;
  let detailRequestCount = 0;
  const detail = buildCameraDetail();
  const page = buildCameraPage();

  return [
    http.get(camerasUrl, ({ request }) => {
      listRequestCount += 1;
      const instance = new URL(request.url).pathname;

      if (scenario === "dependency-unavailable") {
        return unavailableProblem(instance);
      }
      if (scenario === "initial-failure" && listRequestCount === 1) {
        return unavailableProblem(instance);
      }
      if (scenario === "background-refresh-failure" && listRequestCount > 1) {
        return unavailableProblem(instance);
      }
      if (scenario === "empty-list" || scenario === "search-no-results") {
        return jsonResponse(
          buildCameraPage({
            items: [],
            page: Number(new URL(request.url).searchParams.get("page") ?? 1),
            total: 0,
          }),
        );
      }
      return jsonResponse(page);
    }),

    http.post(camerasUrl, ({ request }) => {
      const instance = new URL(request.url).pathname;
      if (scenario === "dependency-unavailable") {
        return unavailableProblem(instance);
      }
      if (scenario === "nested-validation-error") {
        return problemResponse(
          buildProblem({
            status: 422,
            code: "VALIDATION_ERROR",
            instance,
            title: "请求字段验证失败",
            errors: [
              {
                field: "sources[1].name",
                code: "REQUIRED",
                detail: "该字段为必填项。",
              },
              {
                field: "sources[1].url_suffix",
                code: "DUPLICATE_SOURCE_SUFFIX",
                detail: "规范化后的 Source 后缀不能重复。",
              },
            ],
          }),
        );
      }
      return jsonResponse(detail, 201, {
        "Cache-Control": "no-store",
        Location: `/api/v1/cameras/${detail.camera_id}`,
      });
    }),

    http.get(cameraUrl, ({ request }) => {
      detailRequestCount += 1;
      const instance = new URL(request.url).pathname;
      if (scenario === "dependency-unavailable") {
        return unavailableProblem(instance);
      }
      if (scenario === "initial-failure" && detailRequestCount === 1) {
        return unavailableProblem(instance);
      }
      if (scenario === "background-refresh-failure" && detailRequestCount > 1) {
        return unavailableProblem(instance);
      }
      if (scenario === "camera-not-found") {
        return problemResponse(
          buildProblem({
            status: 404,
            code: "CAMERA_NOT_FOUND",
            instance,
            title: "摄像头不存在",
            context: { camera_id: CAMERA_FIXTURE_IDS.primaryCamera },
          }),
        );
      }
      return jsonResponse(detail, 200, { "Cache-Control": "no-store" });
    }),

    http.put(cameraUrl, ({ request }) => {
      const instance = new URL(request.url).pathname;
      if (scenario === "dependency-unavailable") {
        return unavailableProblem(instance);
      }
      if (scenario === "camera-not-found") {
        return problemResponse(
          buildProblem({
            status: 404,
            code: "CAMERA_NOT_FOUND",
            instance,
            context: { camera_id: CAMERA_FIXTURE_IDS.primaryCamera },
          }),
        );
      }
      if (scenario === "nested-validation-error") {
        return problemResponse(
          buildProblem({
            status: 422,
            code: "VALIDATION_ERROR",
            instance,
            title: "请求字段验证失败",
            errors: [
              {
                field: "sources[1].source_id",
                code: "SOURCE_NOT_OWNED_BY_CAMERA",
                detail: "该 Source 不属于当前 Camera。",
              },
            ],
          }),
        );
      }
      return jsonResponse(detail, 200, { "Cache-Control": "no-store" });
    }),

    http.patch(defaultSourceUrl, ({ request }) => {
      const instance = new URL(request.url).pathname;
      if (scenario === "dependency-unavailable") {
        return unavailableProblem(instance);
      }
      if (scenario === "camera-not-found") {
        return problemResponse(
          buildProblem({
            status: 404,
            code: "CAMERA_NOT_FOUND",
            instance,
            context: { camera_id: CAMERA_FIXTURE_IDS.primaryCamera },
          }),
        );
      }
      return jsonResponse(buildDefaultPreviewSourceResponse(detail));
    }),

    http.delete(cameraUrl, ({ request }) => {
      const instance = new URL(request.url).pathname;
      if (scenario === "dependency-unavailable") {
        return unavailableProblem(instance);
      }
      if (scenario === "camera-not-found") {
        return problemResponse(
          buildProblem({
            status: 404,
            code: "CAMERA_NOT_FOUND",
            instance,
            context: { camera_id: CAMERA_FIXTURE_IDS.primaryCamera },
          }),
        );
      }
      return new HttpResponse(null, { status: 204, headers: successHeaders });
    }),
  ];
}
