import { expect, test } from "vitest";

import { cameraListPageSizeForViewport } from "@/features/cameras/components/camera-list-page-size";

test.each([
  [320, 4],
  [519, 4],
  [520, 6],
  [1199, 6],
  [1200, 12],
  [1440, 12],
])("%dpx 视口首次缺省 page_size 为 %d", (viewportWidth, pageSize) => {
  expect(cameraListPageSizeForViewport(viewportWidth)).toBe(pageSize);
});
