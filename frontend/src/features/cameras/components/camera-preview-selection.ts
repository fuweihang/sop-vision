import type {
  CameraDetail,
  CameraSourceDetail,
} from "@/features/cameras/api/cameras-api";

export type CameraPreviewSelection =
  { kind: "default" } | { kind: "temporary"; sourceId: string };

export interface CameraPreviewResolution {
  source: CameraSourceDetail | null;
  /** 临时 Source 已被删除或不可播放时为 true，调用方需把选择状态恢复为 default。 */
  temporarySelectionLost: boolean;
}

/**
 * 播放入口必须同时满足运行状态和地址条件。虽然 Backend 正常响应会让两者保持一致，Frontend
 * 仍同时检查，避免损坏或过渡态响应为离线 Source 创建 WHEP Session。
 */
export function isCameraSourcePlayable(source: CameraSourceDetail) {
  return source.status === "ONLINE" && source.whep_url !== null;
}

export function findCameraDefaultSource(camera: CameraDetail) {
  return camera.sources.find(
    (source) => source.source_id === camera.default_preview_source_id,
  );
}

/**
 * 把持久化默认源和当前页临时选择解析为实际播放 Source。响应数组顺序就是 Backend 保存顺序，
 * 因此默认源不可播放时直接取第一路可播放 Source，不再另行排序。
 */
export function resolveCameraPreviewSource(
  camera: CameraDetail,
  defaultSource: CameraSourceDetail,
  selection: CameraPreviewSelection,
): CameraPreviewResolution {
  if (selection.kind === "temporary") {
    const temporarySource = camera.sources.find(
      (source) => source.source_id === selection.sourceId,
    );
    if (
      temporarySource !== undefined &&
      isCameraSourcePlayable(temporarySource)
    ) {
      return { source: temporarySource, temporarySelectionLost: false };
    }
  }

  const source = isCameraSourcePlayable(defaultSource)
    ? defaultSource
    : (camera.sources.find(isCameraSourcePlayable) ?? null);

  return {
    source,
    temporarySelectionLost: selection.kind === "temporary",
  };
}
