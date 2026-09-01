import { describe, expect, test } from "vitest";

import {
  CAMERA_LIST_GC_TIME,
  CAMERA_LIST_REFETCH_INTERVAL,
  CAMERA_LIST_STALE_TIME,
  cameraListQueryOptions,
  shouldRetryCameraListQuery,
} from "@/features/cameras/api/camera-list-query";
import { apiClient } from "@/lib/api-client";
import {
  ApiProblemError,
  ApiTransportError,
  ApiUnexpectedResponseError,
} from "@/lib/api-errors";
import { buildProblem } from "@/mocks/cameras/fixtures";

describe("Camera 列表 Query", () => {
  test("loader 和页面可复用完整查询身份与可见页面刷新设置", () => {
    const options = cameraListQueryOptions(
      { q: "洗手区", page: 2, page_size: 10 },
      apiClient,
    );

    expect(options.queryKey).toEqual([
      "cameras",
      { q: "洗手区", page: 2, page_size: 10 },
    ]);
    expect(options.staleTime).toBe(CAMERA_LIST_STALE_TIME);
    expect(options.gcTime).toBe(CAMERA_LIST_GC_TIME);
    expect(options.refetchInterval).toBe(CAMERA_LIST_REFETCH_INTERVAL);
    expect(options.refetchIntervalInBackground).toBe(false);
  });

  test("网络错误和可信数据库 503 只自动重试一次", () => {
    const databaseUnavailable = new ApiProblemError(
      buildProblem({
        status: 503,
        code: "DATABASE_UNAVAILABLE",
        instance: "/api/v1/cameras",
      }),
    );

    expect(shouldRetryCameraListQuery(0, new ApiTransportError())).toBe(true);
    expect(shouldRetryCameraListQuery(0, databaseUnavailable)).toBe(true);
    expect(shouldRetryCameraListQuery(1, databaseUnavailable)).toBe(false);
  });

  test("422、聚合损坏、非法响应和程序错误不自动重试", () => {
    const validationError = new ApiProblemError(
      buildProblem({
        status: 422,
        code: "VALIDATION_ERROR",
        instance: "/api/v1/cameras",
      }),
    );
    const aggregateInvalid = new ApiProblemError(
      buildProblem({
        status: 500,
        code: "CAMERA_AGGREGATE_INVALID",
        instance: "/api/v1/cameras",
      }),
    );

    expect(shouldRetryCameraListQuery(0, validationError)).toBe(false);
    expect(shouldRetryCameraListQuery(0, aggregateInvalid)).toBe(false);
    expect(
      shouldRetryCameraListQuery(0, new ApiUnexpectedResponseError(500)),
    ).toBe(false);
    expect(shouldRetryCameraListQuery(0, new Error("程序错误"))).toBe(false);
  });
});
