export const CAMERA_LIST_SINGLE_COLUMN_MAX_WIDTH = 519;
export const CAMERA_LIST_WIDE_MIN_WIDTH = 1200;

/**
 * 首次缺省进入列表时，让每页数量与 Card Grid 的 4/2/1 列断点对应。
 *
 * 宽屏和中屏各显示三行，紧凑视口显示四行。这里使用 viewport width，是因为现有 Tailwind
 * Grid 同样使用 viewport media query；如果将来改为 container query，必须同步调整本函数。
 */
export function cameraListPageSizeForViewport(viewportWidth: number) {
  if (viewportWidth >= CAMERA_LIST_WIDE_MIN_WIDTH) {
    return 12;
  }

  if (viewportWidth > CAMERA_LIST_SINGLE_COLUMN_MAX_WIDTH) {
    return 6;
  }

  return 4;
}

/**
 * Zod 的函数默认值只在 URL 缺少 page_size 时执行，因此 loader 首次请求即可使用正确数量，
 * 不需要页面渲染后再导航和补发请求。非浏览器环境采用设计系统 1280px 基线对应的 12。
 */
export function initialCameraListPageSize() {
  const viewportWidth =
    typeof window === "undefined" ? 1280 : window.innerWidth;

  return cameraListPageSizeForViewport(viewportWidth);
}
