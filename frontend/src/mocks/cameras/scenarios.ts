import {
  http,
  HttpResponse,
  type JsonBodyType,
  type RequestHandler,
} from "msw";

import type {
  CameraUpdateRequest,
  SetDefaultPreviewSourceRequest,
} from "@/features/cameras/api/cameras-api";
import { apiBaseUrl } from "@/lib/api-client";
import {
  buildCameraDetail,
  buildCameraPage,
  buildCameraSummary,
  buildDefaultPreviewSourceResponse,
  buildProblem,
  CAMERA_FIXTURE_IDS,
  CAMERA_FIXTURE_TRACE_ID,
} from "@/mocks/cameras/fixtures";

export const CAMERAS_MSW_SCENARIO_NAMES = [
  "success",
  "empty-list",
  "search-no-results",
  "multi-page",
  "out-of-range",
  "nested-validation-error",
  "camera-not-found",
  "aggregate-invalid",
  "dependency-unavailable",
  "initial-failure",
  "page-error-recovery",
  "background-refresh-failure",
  "whep-player",
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

export const WHEP_TEST_PRIMARY_URL =
  "http://127.0.0.1:8889/whep-test-primary/whep";
export const WHEP_TEST_SECONDARY_URL =
  "http://127.0.0.1:8889/whep-test-secondary/whep";
export const WHEP_TEST_WHEP_URLS = [
  WHEP_TEST_PRIMARY_URL,
  WHEP_TEST_SECONDARY_URL,
] as const;

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
  const initialDetail =
    scenario === "whep-player"
      ? buildCameraDetail({
          sources: [
            {
              name: "动态测试图",
              status: "ONLINE",
              whep_url: WHEP_TEST_PRIMARY_URL,
            },
            {
              name: "彩条测试图",
              status: "ONLINE",
              whep_url: WHEP_TEST_SECONDARY_URL,
            },
          ],
        })
      : buildCameraDetail();
  let configuredDetail = initialDetail;
  let defaultPreviewSourceId = initialDetail.default_preview_source_id;

  /**
   * PUT 和 PATCH 只改变当前场景闭包中的最小验收状态。后续 GET 每次重新投影
   * Detail 和列表摘要，既能模拟服务端最终读取结果，又不会把可变状态扩散到
   * 其他测试、localStorage 或通用 Mock Store。
   */
  function currentDetail() {
    return {
      ...configuredDetail,
      default_preview_source_id: defaultPreviewSourceId,
      sources: configuredDetail.sources.map((source) => ({
        ...source,
        is_default_preview: source.source_id === defaultPreviewSourceId,
      })),
    };
  }

  function currentPage() {
    // 列表摘要必须由同一份 Detail 投影。尤其是 whep-player 场景，Card 和 Detail 只有拿到
    // 相同 source_id+whep_url，浏览器冒烟测试才能真实验证路由切换时复用 Session。
    return buildCameraPage({ items: [buildCameraSummary(currentDetail())] });
  }
  const secondarySummary = buildCameraSummary(
    buildCameraDetail({
      cameraId: CAMERA_FIXTURE_IDS.secondaryCamera,
      name: "包装区 02",
      ipAddress: "192.0.2.65",
      sources: [
        {
          source_id: CAMERA_FIXTURE_IDS.tertiarySource,
          name: "包装区主码流",
          status: "ONLINE",
        },
      ],
    }),
  );

  return [
    http.get(camerasUrl, ({ request }) => {
      listRequestCount += 1;
      const instance = new URL(request.url).pathname;

      if (scenario === "dependency-unavailable") {
        return unavailableProblem(instance);
      }
      if (scenario === "aggregate-invalid") {
        return problemResponse(
          buildProblem({
            status: 500,
            code: "CAMERA_AGGREGATE_INVALID",
            instance,
            title: "摄像头数据无效",
          }),
        );
      }
      if (scenario === "initial-failure" && listRequestCount === 1) {
        return unavailableProblem(instance);
      }
      if (scenario === "page-error-recovery" && listRequestCount <= 2) {
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
      if (scenario === "multi-page") {
        const url = new URL(request.url);
        const requestedPage = Number(url.searchParams.get("page") ?? 1);
        const requestedPageSize = Number(
          url.searchParams.get("page_size") ?? 20,
        );
        return jsonResponse(
          buildCameraPage({
            items:
              requestedPage === 1
                ? currentPage().items
                : requestedPage === 2
                  ? [secondarySummary]
                  : [],
            page: requestedPage,
            pageSize: requestedPageSize,
            total: 2,
          }),
        );
      }
      if (scenario === "out-of-range") {
        const url = new URL(request.url);
        return jsonResponse(
          buildCameraPage({
            items: [],
            page: Number(url.searchParams.get("page") ?? 3),
            pageSize: Number(url.searchParams.get("page_size") ?? 1),
            total: 2,
          }),
        );
      }
      return jsonResponse(currentPage());
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
                detail: "规范化后的视频源后缀不能重复。",
              },
            ],
          }),
        );
      }
      const detail = currentDetail();
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
      return jsonResponse(currentDetail(), 200, {
        "Cache-Control": "no-store",
      });
    }),

    http.put(cameraUrl, async ({ request }) => {
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
                detail: "该视频源不属于当前摄像头。",
              },
            ],
          }),
        );
      }
      const body = (await request.json()) as CameraUpdateRequest;
      const currentSourcesById = new Map(
        configuredDetail.sources.map((source) => [source.source_id, source]),
      );
      const existingSources = body.sources.flatMap((source) => {
        const currentSource = source.source_id
          ? currentSourcesById.get(source.source_id)
          : undefined;

        /**
         * 这个可变状态只服务双路既有 Source 的浏览器验收。新增和删除的服务端规则
         * 已由 Backend 自动化测试覆盖，Mock 不分配 ID，也不复制第二份领域校验。
         */
        if (!currentSource) {
          return [];
        }

        return [
          {
            ...currentSource,
            name: source.name,
            url_suffix: source.url_suffix,
          },
        ];
      });
      const defaultSourceIndex = existingSources.findIndex(
        (source) =>
          body.sources.find(
            (requestSource) => requestSource.source_id === source.source_id,
          )?.is_default_preview === true,
      );

      if (existingSources.length > 0 && defaultSourceIndex >= 0) {
        configuredDetail = buildCameraDetail({
          cameraId: configuredDetail.camera_id,
          name: body.name,
          ipAddress: body.ip_address,
          rtspPort: body.rtsp_port,
          username: body.username,
          password: body.password,
          sources: existingSources,
          defaultSourceIndex,
          createdAt: configuredDetail.created_at,
          updatedAt: configuredDetail.updated_at,
        });
        defaultPreviewSourceId = configuredDetail.default_preview_source_id;
      }

      return jsonResponse(currentDetail(), 200, {
        "Cache-Control": "no-store",
      });
    }),

    http.patch(defaultSourceUrl, async ({ request }) => {
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
      if (scenario === "aggregate-invalid") {
        return problemResponse(
          buildProblem({
            status: 500,
            code: "CAMERA_AGGREGATE_INVALID",
            instance,
            title: "摄像头数据无效",
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
                field: "source_id",
                code: "SOURCE_NOT_OWNED_BY_CAMERA",
                detail: "Source 不存在或不属于当前 Camera。",
              },
            ],
          }),
        );
      }

      const body = (await request.json()) as SetDefaultPreviewSourceRequest;
      if (
        !configuredDetail.sources.some(
          (source) => source.source_id === body.source_id,
        )
      ) {
        return problemResponse(
          buildProblem({
            status: 422,
            code: "VALIDATION_ERROR",
            instance,
            title: "请求字段验证失败",
            errors: [
              {
                field: "source_id",
                code: "SOURCE_NOT_OWNED_BY_CAMERA",
                detail: "Source 不存在或不属于当前 Camera。",
              },
            ],
          }),
        );
      }
      defaultPreviewSourceId = body.source_id;
      return jsonResponse(
        buildDefaultPreviewSourceResponse(currentDetail(), body.source_id),
      );
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
