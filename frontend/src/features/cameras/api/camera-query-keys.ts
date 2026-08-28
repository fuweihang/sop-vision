import {
  normalizeCameraListQuery,
  type CameraListQuery,
} from "@/features/cameras/api/cameras-api";

/**
 * Foundation 冻结的全部 Cameras Query Key。
 *
 * 不提供 all/root/sort 等额外变体，后续切片只能通过这三个工厂形成缓存身份。调用方若需按
 * 前缀失效，可直接使用第一段常量，不必为失效便利扩展公共 Key 契约。
 */
export const cameraQueryKeys = {
  cameras: (query: CameraListQuery = {}) =>
    ["cameras", normalizeCameraListQuery(query)] as const,
  camera: (cameraId: string) => ["camera", cameraId] as const,
  playback: (sourceId: string) => ["playback", sourceId] as const,
};
