import { expect, test } from "vitest";

import {
  cameraEditFormSchema,
  createEmptyCameraEditSource,
  toCameraEditFormValues,
  toCameraUpdateRequest,
} from "@/features/cameras/forms/camera-edit-form";
import { buildCameraDetail } from "@/mocks/cameras/fixtures";

test("详情只投影可编辑字段并保留既有 Source ID 与顺序", () => {
  const camera = buildCameraDetail();

  const values = toCameraEditFormValues(camera);

  expect(values).toEqual({
    name: camera.name,
    ip_address: camera.ip_address,
    rtsp_port: camera.rtsp_port,
    username: camera.username,
    password: camera.password,
    sources: camera.sources.map((source) => ({
      source_id: source.source_id,
      name: source.name,
      url_suffix: source.url_suffix,
      is_default_preview: source.is_default_preview,
    })),
  });
  expect(JSON.stringify(values)).not.toContain("rtsp_url");
  expect(JSON.stringify(values)).not.toContain("whep_url");
});

test("PUT 转换保留既有 ID、忽略 UI key，并让新增 Source 缺省 ID", () => {
  const camera = buildCameraDetail();
  const input = toCameraEditFormValues(camera);
  const existing = input.sources[1];
  if (existing === undefined) {
    throw new Error("测试 Camera 缺少第二路 Source。");
  }
  input.sources = [
    existing,
    {
      ...createEmptyCameraEditSource(),
      name: " 新增 Source ",
      url_suffix: " /new/source ",
    },
  ];
  input.sources[0]!.is_default_preview = true;

  const result = cameraEditFormSchema.safeParse(input);
  expect(result.success).toBe(true);
  if (!result.success) {
    return;
  }

  const request = toCameraUpdateRequest(result.data);
  expect(request.sources).toEqual([
    {
      source_id: existing.source_id,
      name: existing.name,
      url_suffix: existing.url_suffix,
      is_default_preview: true,
    },
    {
      name: "新增 Source",
      url_suffix: "new/source",
      is_default_preview: false,
    },
  ]);
  expect(request.sources[1]).not.toHaveProperty("id");
  expect(request.sources[1]).not.toHaveProperty("source_id");
});

test("编辑 Schema 继续检查至少一路、唯一默认和规范化后缀重复", () => {
  const camera = buildCameraDetail();
  const emptyResult = cameraEditFormSchema.safeParse({
    ...toCameraEditFormValues(camera),
    sources: [],
  });
  expect(emptyResult.success).toBe(false);

  const duplicateValues = toCameraEditFormValues(camera);
  duplicateValues.sources[0]!.is_default_preview = true;
  duplicateValues.sources[1]!.is_default_preview = true;
  duplicateValues.sources[1]!.url_suffix = `/${duplicateValues.sources[0]!.url_suffix}`;
  const duplicateResult = cameraEditFormSchema.safeParse(duplicateValues);
  expect(duplicateResult.success).toBe(false);
  if (duplicateResult.success) {
    return;
  }
  expect(
    duplicateResult.error.issues.map((issue) => ({
      path: issue.path,
      message: issue.message,
    })),
  ).toEqual(
    expect.arrayContaining([
      {
        path: ["sources", 1, "is_default_preview"],
        message: "只能选择一路默认预览源。",
      },
      {
        path: ["sources", 1, "url_suffix"],
        message: "URL 后缀不能与第 1 路视频源重复。",
      },
    ]),
  );
});
