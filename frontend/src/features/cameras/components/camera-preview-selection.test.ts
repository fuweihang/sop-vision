import { expect, test } from "vitest";

import {
  findCameraDefaultSource,
  isCameraSourcePlayable,
  resolveCameraPreviewSource,
  type CameraPreviewSelection,
} from "@/features/cameras/components/camera-preview-selection";
import { buildCameraDetail } from "@/mocks/cameras/fixtures";

function resolve(
  selection: CameraPreviewSelection,
  camera = buildCameraDetail(),
) {
  const defaultSource = findCameraDefaultSource(camera);
  if (defaultSource === undefined) {
    throw new Error("测试 Camera 缺少默认 Source。");
  }
  return resolveCameraPreviewSource(camera, defaultSource, selection);
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

test("默认源可播放时优先默认源，否则按响应顺序回退第一路可播放源", () => {
  const availableDefault = buildCameraDetail({
    sources: [{ status: "ONLINE" }, { status: "ONLINE" }],
    defaultSourceIndex: 1,
  });
  expect(resolve({ kind: "default" }, availableDefault).source?.source_id).toBe(
    availableDefault.default_preview_source_id,
  );

  const unavailableDefault = buildCameraDetail({
    sources: [
      { status: "OFFLINE" },
      { status: "ONLINE" },
      { status: "ONLINE" },
    ],
  });
  expect(
    resolve({ kind: "default" }, unavailableDefault).source?.source_id,
  ).toBe(unavailableDefault.sources[1]?.source_id);
});

test("保留仍可播放的临时选择，选择失效时回到默认规则", () => {
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
    unavailableCamera.default_preview_source_id,
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

  expect(resolve({ kind: "default" }, camera).source).toBeNull();
});
