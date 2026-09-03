import { QueryClient, QueryObserver } from "@tanstack/react-query";
import axios, {
  AxiosHeaders,
  type AxiosAdapter,
  type InternalAxiosRequestConfig,
} from "axios";
import { afterEach, describe, expect, test, vi } from "vitest";

import {
  CAMERA_DETAIL_GC_TIME,
  CAMERA_DETAIL_REFETCH_INTERVAL,
  CAMERA_DETAIL_STALE_TIME,
  cameraDetailQueryOptions,
  shouldRetryCameraDetailQuery,
} from "@/features/cameras/api/camera-detail-query";
import {
  ApiProblemError,
  ApiTransportError,
  ApiUnexpectedResponseError,
  type ProblemDetails,
} from "@/lib/api-errors";
import {
  buildCameraDetail,
  CAMERA_FIXTURE_IDS,
} from "@/mocks/cameras/fixtures";
import { setDocumentVisibility } from "../../support/browser-mocks";

const detail = buildCameraDetail();

function createDetailClient() {
  const requests: InternalAxiosRequestConfig[] = [];
  const adapter: AxiosAdapter = (config: InternalAxiosRequestConfig) => {
    requests.push(config);
    return Promise.resolve({
      data: detail,
      status: 200,
      statusText: "OK",
      headers: new AxiosHeaders({ "Cache-Control": "no-store" }),
      config,
    });
  };

  return { client: axios.create({ adapter }), requests };
}

function problem(status: number, code: string): ProblemDetails {
  return {
    type: `urn:sop-vision:problem:${code.toLowerCase()}`,
    title: "测试错误",
    status,
    code,
    detail: "用于验证重试分类。",
    instance: `/api/v1/cameras/${CAMERA_FIXTURE_IDS.primaryCamera}`,
    trace_id: "tr_camera_detail_query_test",
    errors: [],
    context: {},
  };
}

afterEach(() => {
  vi.useRealTimers();
  setDocumentVisibility("visible");
});

describe("Camera 详情 Query Options", () => {
  test("固定刷新参数并使用注入的 Client", async () => {
    const { client, requests } = createDetailClient();
    const options = cameraDetailQueryOptions(
      CAMERA_FIXTURE_IDS.primaryCamera,
      client,
    );
    const queryClient = new QueryClient();

    await expect(queryClient.fetchQuery(options)).resolves.toEqual(detail);

    expect(options.staleTime).toBe(CAMERA_DETAIL_STALE_TIME);
    expect(options.gcTime).toBe(CAMERA_DETAIL_GC_TIME);
    expect(options.refetchInterval).toBe(CAMERA_DETAIL_REFETCH_INTERVAL);
    expect(options.refetchIntervalInBackground).toBe(false);
    expect(requests).toHaveLength(1);
    expect(requests[0]?.url).toBe(
      `/cameras/${CAMERA_FIXTURE_IDS.primaryCamera}`,
    );

    queryClient.clear();
  });

  test.each([
    ["可信 404", 0, new ApiProblemError(problem(404, "CAMERA_NOT_FOUND"))],
    ["可信 422", 0, new ApiProblemError(problem(422, "VALIDATION_ERROR"))],
    [
      "损坏聚合",
      0,
      new ApiProblemError(problem(500, "CAMERA_AGGREGATE_INVALID")),
    ],
    ["意外响应", 0, new ApiUnexpectedResponseError(502)],
    ["未知程序错误", 0, new TypeError("测试程序错误")],
  ])("%s 不重试", (_name, failureCount, error) => {
    expect(shouldRetryCameraDetailQuery(failureCount, error)).toBe(false);
  });

  test.each([
    ["网络失败", new ApiTransportError()],
    ["数据库不可用", new ApiProblemError(problem(503, "DATABASE_UNAVAILABLE"))],
  ])("%s 最多自动重试一次", (_name, error) => {
    expect(shouldRetryCameraDetailQuery(0, error)).toBe(true);
    expect(shouldRetryCameraDetailQuery(1, error)).toBe(false);
  });

  test("页面隐藏时暂停轮询，重新可见后恢复下一次轮询", async () => {
    vi.useFakeTimers();
    const { client, requests } = createDetailClient();
    const queryClient = new QueryClient();
    const options = cameraDetailQueryOptions(
      CAMERA_FIXTURE_IDS.primaryCamera,
      client,
    );
    await queryClient.fetchQuery(options);
    const observer = new QueryObserver(queryClient, options);
    const unsubscribe = observer.subscribe(() => undefined);

    setDocumentVisibility("hidden");
    await vi.advanceTimersByTimeAsync(CAMERA_DETAIL_REFETCH_INTERVAL);
    expect(requests).toHaveLength(1);

    setDocumentVisibility("visible");
    await vi.advanceTimersByTimeAsync(CAMERA_DETAIL_REFETCH_INTERVAL);
    expect(requests).toHaveLength(2);

    unsubscribe();
    queryClient.clear();
  });

  test("最后一个订阅卸载后按五分钟进入缓存回收", async () => {
    vi.useFakeTimers();
    const { client } = createDetailClient();
    const queryClient = new QueryClient();
    const options = cameraDetailQueryOptions(
      CAMERA_FIXTURE_IDS.primaryCamera,
      client,
    );
    await queryClient.fetchQuery(options);
    const observer = new QueryObserver(queryClient, options);
    const unsubscribe = observer.subscribe(() => undefined);
    unsubscribe();

    await vi.advanceTimersByTimeAsync(CAMERA_DETAIL_GC_TIME - 1);
    expect(queryClient.getQueryData(options.queryKey)).toEqual(detail);

    await vi.advanceTimersByTimeAsync(1);
    expect(queryClient.getQueryData(options.queryKey)).toBeUndefined();

    queryClient.clear();
  });
});
