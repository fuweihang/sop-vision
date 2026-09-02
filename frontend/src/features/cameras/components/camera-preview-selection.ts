import type {
  CameraDetail,
  CameraSourceDetail,
} from "@/features/cameras/api/cameras-api";

export type CameraPreviewSelection =
  { kind: "automatic" } | { kind: "temporary"; sourceId: string };

export interface CameraPreviewResolution {
  source: CameraSourceDetail | null;
  /** 临时 Source 已被删除或不可播放时为 true，调用方需把选择状态恢复为 automatic。 */
  temporarySelectionLost: boolean;
}

/**
 * 播放入口必须同时满足运行状态和地址条件。虽然 Backend 正常响应会让两者保持一致，Frontend
 * 仍同时检查，避免损坏或过渡态响应为离线 Source 创建 WHEP Session。
 */
export function isCameraSourcePlayable(source: CameraSourceDetail) {
  return source.status === "ONLINE" && source.whep_url !== null;
}

/**
 * 把详情页自动选择和当前页临时选择解析为实际播放 Source。Backend 已按 sort_order 返回 Source，
 * 因此自动选择只取响应顺序中的第一路可播放 Source，不读取仅供 Card 预览使用的默认源 ID。
 */
export function resolveCameraPreviewSource(
  camera: CameraDetail,
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

  const source = camera.sources.find(isCameraSourcePlayable) ?? null;

  return {
    source,
    temporarySelectionLost: selection.kind === "temporary",
  };
}
