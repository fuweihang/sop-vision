import {
  normalizeCameraListQuery,
  type CameraListQuery,
} from "@/features/cameras/api/cameras-api";

/**
 * Cameras 当前使用的两类稳定 Query Key。
 *
 * 不提供 all/root/sort 等额外变体，后续能力只能通过这些工厂形成缓存身份。调用方若需按
 * 前缀失效，可直接使用第一段常量，不必为失效便利扩展公共 Key 契约。
 */
export const cameraQueryKeys = {
  cameras: (query: CameraListQuery = {}) =>
    ["cameras", normalizeCameraListQuery(query)] as const,
  camera: (cameraId: string) => ["camera", cameraId] as const,
};
