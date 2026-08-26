import { expect, test } from "vitest";

import { apiBaseUrl } from "@/lib/api-client";
import { ApiProblemError } from "@/lib/api-errors";
import {
  createCamera,
  deleteCamera,
  getCamera,
  getCameraSourcePlayback,
  listCameras,
  setDefaultPreviewSource,
  updateCamera,
} from "@/lib/cameras-api";
import {
  buildCameraCreateRequest,
  buildCameraUpdateRequest,
  CAMERA_FIXTURE_IDS,
} from "@/mocks/cameras/fixtures";
import { createCamerasMswScenario } from "@/mocks/cameras/scenarios";
import { mockServer } from "@/mocks/node";

function useScenario(name: Parameters<typeof createCamerasMswScenario>[0]) {
  mockServer.use(...createCamerasMswScenario(name));
}

async function captureProblem(promise: Promise<unknown>) {
  try {
    await promise;
  } catch (error: unknown) {
    expect(error).toBeInstanceOf(ApiProblemError);
    if (error instanceof ApiProblemError) {
      return error;
    }
  }
  throw new Error("请求应返回结构化 ApiProblemError。");
}

test("成功场景覆盖七个 Cameras operation", async () => {
  useScenario("success");

  const page = await listCameras();
  const created = await createCamera(buildCameraCreateRequest());
  const detail = await getCamera(CAMERA_FIXTURE_IDS.primaryCamera);
  const updated = await updateCamera(
    CAMERA_FIXTURE_IDS.primaryCamera,
    buildCameraUpdateRequest(),
  );
  const defaultSource = await setDefaultPreviewSource(
    CAMERA_FIXTURE_IDS.primaryCamera,
    { source_id: CAMERA_FIXTURE_IDS.primarySource },
  );
  await deleteCamera(CAMERA_FIXTURE_IDS.primaryCamera);
  const playback = await getCameraSourcePlayback(
    CAMERA_FIXTURE_IDS.primarySource,
  );

  expect(page.total).toBe(1);
  expect(created.camera_id).toBe(CAMERA_FIXTURE_IDS.primaryCamera);
  expect(detail.password).toBeDefined();
  expect(updated.source_count).toBe(2);
  expect(defaultSource.default_preview_source_id).toBe(
    CAMERA_FIXTURE_IDS.primarySource,
  );
  expect(playback.status).toBe("AVAILABLE");
});

test("空列表与搜索无结果是可独立选择的确定场景", async () => {
  useScenario("empty-list");
  await expect(listCameras()).resolves.toMatchObject({ items: [], total: 0 });

  mockServer.resetHandlers();
  useScenario("search-no-results");
  await expect(listCameras({ q: "不存在" })).resolves.toMatchObject({
    items: [],
    total: 0,
  });
});

test("嵌套 422 保留字段路径并通过 Client 严格 Problem 边界", async () => {
  useScenario("nested-validation-error");
  const error = await captureProblem(createCamera(buildCameraCreateRequest()));

  expect(error.problem.status).toBe(422);
  expect(error.problem.code).toBe("VALIDATION_ERROR");
  expect(error.problem.errors).toEqual([
    expect.objectContaining({ field: "sources[1].name", code: "REQUIRED" }),
    expect.objectContaining({
      field: "sources[1].url_suffix",
      code: "DUPLICATE_SOURCE_SUFFIX",
    }),
  ]);
});

test.each([
  ["camera-not-found", "camera", 404, "CAMERA_NOT_FOUND"],
  ["source-not-found", "playback", 404, "SOURCE_NOT_FOUND"],
  ["playback-not-available", "playback", 409, "PLAYBACK_NOT_AVAILABLE"],
  [
    "playback-invalid-response",
    "playback",
    502,
    "MEDIA_SERVICE_INVALID_RESPONSE",
  ],
  ["dependency-unavailable", "camera", 503, "DATABASE_UNAVAILABLE"],
  ["dependency-unavailable", "playback", 503, "MEDIA_SERVICE_UNAVAILABLE"],
] as const)(
  "%s 返回稳定的 %i Problem",
  async (scenario, operation, status, code) => {
    useScenario(scenario);
    const promise =
      operation === "camera"
        ? getCamera(CAMERA_FIXTURE_IDS.primaryCamera)
        : getCameraSourcePlayback(CAMERA_FIXTURE_IDS.primarySource);
    const error = await captureProblem(promise);

    expect(error.problem.status).toBe(status);
    expect(error.problem.code).toBe(code);
    if (status === 409) {
      expect(error.retryAfterSeconds).toBe(2);
    }
  },
);

test("首次失败与后台刷新失败按独立计数器返回确定序列", async () => {
  useScenario("initial-failure");
  await expect(listCameras()).rejects.toBeInstanceOf(ApiProblemError);
  await expect(listCameras()).resolves.toMatchObject({ total: 1 });

  mockServer.resetHandlers();
  useScenario("background-refresh-failure");
  await expect(listCameras()).resolves.toMatchObject({ total: 1 });
  const error = await captureProblem(listCameras());
  expect(error.problem.code).toBe("DATABASE_UNAVAILABLE");
});

test("未处理请求直接失败而不透传到真实网络", async () => {
  await expect(
    fetch(`${apiBaseUrl.replace(/\/$/, "")}/unhandled-foundation-probe`),
  ).rejects.toThrow();
});
