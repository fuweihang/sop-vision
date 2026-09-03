import { expect, test, vi } from "vitest";

import { apiBaseUrl } from "@/lib/api-client";
import { ApiProblemError } from "@/lib/api-errors";
import {
  createCamera,
  deleteCamera,
  getCamera,
  listCameras,
  setDefaultPreviewSource,
  updateCamera,
} from "@/features/cameras/api/cameras-api";
import {
  buildCameraCreateRequest,
  buildCameraUpdateRequest,
  CAMERA_FIXTURE_IDS,
  CAMERA_FIXTURE_SECRET,
} from "@/mocks/cameras/fixtures";
import {
  createCamerasMswScenario,
  WHEP_TEST_PRIMARY_URL,
  WHEP_TEST_SECONDARY_URL,
} from "@/mocks/cameras/scenarios";
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

test("成功场景覆盖六个 Cameras operation", async () => {
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
    { source_id: CAMERA_FIXTURE_IDS.secondarySource },
  );
  await deleteCamera(CAMERA_FIXTURE_IDS.primaryCamera);

  expect(page.total).toBe(1);
  expect(created.camera_id).toBe(CAMERA_FIXTURE_IDS.primaryCamera);
  expect(detail.password).toBeDefined();
  expect(updated.source_count).toBe(2);
  expect(defaultSource.default_preview_source_id).toBe(
    CAMERA_FIXTURE_IDS.secondarySource,
  );
});

test("MSW 非详情响应不携带唯一泄漏哨兵或完整 RTSP 配置", async () => {
  useScenario("success");

  const nonDetailPayloads: unknown[] = [
    await listCameras(),
    await setDefaultPreviewSource(CAMERA_FIXTURE_IDS.primaryCamera, {
      source_id: CAMERA_FIXTURE_IDS.primarySource,
    }),
  ];

  // Problem 也属于禁止泄密的公共响应。通过真实 MSW handler 和 Client 错误边界取回它，
  // 可以同时防止场景工厂或 Axios 映射未来把敏感详情整对象塞进 context。
  mockServer.resetHandlers();
  useScenario("dependency-unavailable");
  nonDetailPayloads.push((await captureProblem(listCameras())).problem);

  for (const payload of nonDetailPayloads) {
    const serialized = JSON.stringify(payload);
    expect(serialized).not.toContain(CAMERA_FIXTURE_SECRET);
    expect(serialized).not.toContain("fixture-camera-user");
    expect(serialized).not.toContain("url_suffix");
    expect(serialized).not.toContain("rtsp://");
  }
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

test("多页与越界场景保留请求页码、page_size 和真实 total", async () => {
  useScenario("multi-page");
  await expect(listCameras({ page: 2, page_size: 1 })).resolves.toMatchObject({
    page: 2,
    page_size: 1,
    total: 2,
    items: [expect.objectContaining({ name: "包装区 02" })],
  });

  mockServer.resetHandlers();
  useScenario("out-of-range");
  await expect(listCameras({ page: 3, page_size: 1 })).resolves.toMatchObject({
    page: 3,
    page_size: 1,
    total: 2,
    items: [],
  });
});

test("whep-player 场景为两路 Source 提供固定且不同的浏览器播放入口", async () => {
  useScenario("whep-player");
  const page = await listCameras();
  const detail = await getCamera(CAMERA_FIXTURE_IDS.primaryCamera);

  expect(page.items[0]?.default_preview_source).toMatchObject({
    source_id: detail.default_preview_source_id,
    whep_url: WHEP_TEST_PRIMARY_URL,
  });
  expect(detail.sources.map((source) => source.whep_url)).toEqual([
    WHEP_TEST_PRIMARY_URL,
    WHEP_TEST_SECONDARY_URL,
  ]);
});

test("默认源 PATCH 后列表与详情 GET 都投影场景闭包中的最新默认 ID", async () => {
  useScenario("success");

  await setDefaultPreviewSource(CAMERA_FIXTURE_IDS.primaryCamera, {
    source_id: CAMERA_FIXTURE_IDS.secondarySource,
  });
  const [page, detail] = await Promise.all([
    listCameras(),
    getCamera(CAMERA_FIXTURE_IDS.primaryCamera),
  ]);

  expect(page.items[0]?.default_preview_source).toMatchObject({
    source_id: CAMERA_FIXTURE_IDS.secondarySource,
    whep_url: null,
  });
  expect(detail.default_preview_source_id).toBe(
    CAMERA_FIXTURE_IDS.secondarySource,
  );
  expect(
    detail.sources.find(
      (source) => source.source_id === CAMERA_FIXTURE_IDS.secondarySource,
    )?.is_default_preview,
  ).toBe(true);
});

test("PUT 后重新读取保留连接字段、既有 Source 配置和顺序", async () => {
  useScenario("whep-player");
  const beforeUpdate = await getCamera(CAMERA_FIXTURE_IDS.primaryCamera);
  const [primarySource, secondarySource] = beforeUpdate.sources;
  if (!primarySource || !secondarySource) {
    throw new Error("双路 WHEP 场景必须提供两路 Source。");
  }

  await updateCamera(CAMERA_FIXTURE_IDS.primaryCamera, {
    name: "包装区相机 09",
    ip_address: "192.0.2.109",
    rtsp_port: 8554,
    username: "updated-camera-user",
    password: "updated-camera-password",
    sources: [
      {
        source_id: secondarySource.source_id,
        name: "彩条副码流",
        url_suffix: "Streaming/Channels/202",
        is_default_preview: true,
      },
      {
        source_id: primarySource.source_id,
        name: "动态主码流",
        url_suffix: "Streaming/Channels/201",
        is_default_preview: false,
      },
    ],
  });

  const [page, detail] = await Promise.all([
    listCameras(),
    getCamera(CAMERA_FIXTURE_IDS.primaryCamera),
  ]);
  expect(detail).toMatchObject({
    name: "包装区相机 09",
    ip_address: "192.0.2.109",
    rtsp_port: 8554,
    username: "updated-camera-user",
    password: "updated-camera-password",
    default_preview_source_id: secondarySource.source_id,
  });
  expect(
    detail.sources.map((source) => ({
      source_id: source.source_id,
      name: source.name,
      url_suffix: source.url_suffix,
      status: source.status,
      whep_url: source.whep_url,
    })),
  ).toEqual([
    {
      source_id: secondarySource.source_id,
      name: "彩条副码流",
      url_suffix: "Streaming/Channels/202",
      status: secondarySource.status,
      whep_url: secondarySource.whep_url,
    },
    {
      source_id: primarySource.source_id,
      name: "动态主码流",
      url_suffix: "Streaming/Channels/201",
      status: primarySource.status,
      whep_url: primarySource.whep_url,
    },
  ]);
  expect(page.items[0]).toMatchObject({
    name: "包装区相机 09",
    ip_address: "192.0.2.109",
    rtsp_port: 8554,
    default_preview_source: {
      source_id: secondarySource.source_id,
      name: "彩条副码流",
      whep_url: WHEP_TEST_SECONDARY_URL,
    },
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

test("默认源 PATCH 场景覆盖所属校验和聚合损坏 500", async () => {
  useScenario("nested-validation-error");
  let error = await captureProblem(
    setDefaultPreviewSource(CAMERA_FIXTURE_IDS.primaryCamera, {
      source_id: CAMERA_FIXTURE_IDS.tertiarySource,
    }),
  );
  expect(error.problem).toMatchObject({
    status: 422,
    code: "VALIDATION_ERROR",
    errors: [
      expect.objectContaining({
        field: "source_id",
        code: "SOURCE_NOT_OWNED_BY_CAMERA",
      }),
    ],
  });

  mockServer.resetHandlers();
  useScenario("aggregate-invalid");
  error = await captureProblem(
    setDefaultPreviewSource(CAMERA_FIXTURE_IDS.primaryCamera, {
      source_id: CAMERA_FIXTURE_IDS.secondarySource,
    }),
  );
  expect(error.problem).toMatchObject({
    status: 500,
    code: "CAMERA_AGGREGATE_INVALID",
    context: {},
  });
  expect(JSON.stringify(error.problem)).not.toContain(CAMERA_FIXTURE_SECRET);
});

test.each([
  ["camera-not-found", 404, "CAMERA_NOT_FOUND"],
  ["dependency-unavailable", 503, "DATABASE_UNAVAILABLE"],
] as const)("%s 返回稳定的 %i Problem", async (scenario, status, code) => {
  useScenario(scenario);
  const error = await captureProblem(
    getCamera(CAMERA_FIXTURE_IDS.primaryCamera),
  );

  expect(error.problem.status).toBe(status);
  expect(error.problem.code).toBe(code);
});

test("列表聚合损坏返回脱敏且不携带 Camera 身份的 500 Problem", async () => {
  useScenario("aggregate-invalid");
  const error = await captureProblem(listCameras());
  const serialized = JSON.stringify(error.problem);

  expect(error.problem.status).toBe(500);
  expect(error.problem.code).toBe("CAMERA_AGGREGATE_INVALID");
  expect(error.problem.context).toEqual({});
  expect(serialized).not.toContain(CAMERA_FIXTURE_SECRET);
  expect(serialized).not.toContain("camera_id");
  expect(serialized).not.toContain("url_suffix");
});

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
  // MSW 会先把预期的未匹配请求写入 console.error，再拒绝 fetch。这里只屏蔽本用例主动
  // 制造的诊断信息，避免成功的安全边界测试在 CI 中产生误导性的 stderr。
  const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
  try {
    await expect(
      fetch(`${apiBaseUrl.replace(/\/$/, "")}/unhandled-foundation-probe`),
    ).rejects.toThrow();
  } finally {
    consoleError.mockRestore();
  }
});
