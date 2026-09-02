import { expect, test } from "vitest";

import {
  isCameraSourcePlayable,
  resolveCameraPreviewSource,
  type CameraPreviewSelection,
} from "@/features/cameras/components/camera-preview-selection";
import { buildCameraDetail } from "@/mocks/cameras/fixtures";

function resolve(
  selection: CameraPreviewSelection,
  camera = buildCameraDetail(),
) {
  return resolveCameraPreviewSource(camera, selection);
}

test("只有 ONLINE 且包含 WHEP URL 的 Source 才可播放", () => {
  const camera = buildCameraDetail({
    sources: [
      { status: "ONLINE", whep_url: null },
      { status: "OFFLINE", whep_url: "https://media.example.invalid/bad/whep" },
      { status: "ONLINE" },
    ],
  });

  expect(camera.sources.map(isCameraSourcePlayable)).toEqual([
    false,
    false,
    true,
  ]);
});

test("自动选择忽略默认源，按响应顺序取第一路可播放 Source", () => {
  const laterDefault = buildCameraDetail({
    sources: [{ status: "ONLINE" }, { status: "ONLINE" }],
    defaultSourceIndex: 1,
  });
  expect(resolve({ kind: "automatic" }, laterDefault).source?.source_id).toBe(
    laterDefault.sources[0]?.source_id,
  );

  const unavailableFirst = buildCameraDetail({
    sources: [
      { status: "OFFLINE" },
      { status: "ONLINE" },
      { status: "ONLINE" },
    ],
  });
  expect(
    resolve({ kind: "automatic" }, unavailableFirst).source?.source_id,
  ).toBe(unavailableFirst.sources[1]?.source_id);
});

test("保留仍可播放的临时选择，选择失效时回到排序自动选择", () => {
  const camera = buildCameraDetail({
    sources: [{ status: "ONLINE" }, { status: "ONLINE" }],
  });
  const temporarySource = camera.sources[1];
  if (temporarySource === undefined) {
    throw new Error("测试 Camera 缺少临时 Source。");
  }

  expect(
    resolve({ kind: "temporary", sourceId: temporarySource.source_id }, camera),
  ).toEqual({ source: temporarySource, temporarySelectionLost: false });

  const unavailableCamera = {
    ...camera,
    sources: camera.sources.map((source) =>
      source.source_id === temporarySource.source_id
        ? { ...source, status: "OFFLINE" as const, whep_url: null }
        : source,
    ),
  };
  const fallback = resolve(
    { kind: "temporary", sourceId: temporarySource.source_id },
    unavailableCamera,
  );
  expect(fallback.source?.source_id).toBe(
    unavailableCamera.sources[0]?.source_id,
  );
  expect(fallback.temporarySelectionLost).toBe(true);
});

test("全部 Source 不可播放时返回 null", () => {
  const camera = buildCameraDetail({
    sources: [
      { status: "OFFLINE", whep_url: null },
      { status: "ONLINE", whep_url: null },
    ],
  });

  expect(resolve({ kind: "automatic" }, camera).source).toBeNull();
});
