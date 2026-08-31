import { expect, test } from "vitest";

import { calculateRenderedMediaRect } from "@/features/video/geometry/video-geometry";

test("contain 在容器内居中并保留 letterbox", () => {
  const rect = calculateRenderedMediaRect(
    { width: 1920, height: 1080 },
    { width: 1000, height: 1000 },
    "contain",
  );

  expect(rect.x).toBeCloseTo(0);
  expect(rect.y).toBe(218.75);
  expect(rect.width).toBeCloseTo(1000);
  expect(rect.height).toBe(562.5);
});

test("cover 居中裁切超出容器的媒体区域", () => {
  const rect = calculateRenderedMediaRect(
    { width: 1920, height: 1080 },
    { width: 1000, height: 1000 },
    "cover",
  );

  expect(rect.x).toBeCloseTo(-388.889, 3);
  expect(rect.y).toBe(0);
  expect(rect.width).toBeCloseTo(1777.778, 3);
  expect(rect.height).toBe(1000);
});
