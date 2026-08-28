import { describe, expect, test } from "vitest";

import { cameraQueryKeys } from "@/features/cameras/api/camera-query-keys";

describe("Cameras Query Key", () => {
  test("列表 Key 固定默认分页并把空白 q 规范化为未提供", () => {
    expect(cameraQueryKeys.cameras()).toEqual([
      "cameras",
      { q: undefined, page: 1, page_size: 20 },
    ]);
    expect(cameraQueryKeys.cameras({ q: "   " })).toEqual(
      cameraQueryKeys.cameras({ q: null }),
    );
  });

  test("列表 Key 使用 trim 后的 q 且不产生 sort 维度", () => {
    const key = cameraQueryKeys.cameras({
      q: "  Camera 01  ",
      page: 3,
      page_size: 50,
    });

    expect(key).toEqual([
      "cameras",
      { q: "Camera 01", page: 3, page_size: 50 },
    ]);
    expect(key[1]).not.toHaveProperty("sort");
  });

  test("详情与播放 Key 使用各自稳定 ID", () => {
    expect(cameraQueryKeys.camera("camera-id")).toEqual([
      "camera",
      "camera-id",
    ]);
    expect(cameraQueryKeys.playback("source-id")).toEqual([
      "playback",
      "source-id",
    ]);
  });
});
