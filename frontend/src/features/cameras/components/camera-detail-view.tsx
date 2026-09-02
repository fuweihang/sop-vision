import { useState } from "react";
import type { AxiosInstance } from "axios";

import { PageContainer } from "@/components/layout/page-container";
import { PageHeader } from "@/components/layout/page-header";
import type {
  CameraDetail,
  CameraSourceDetail,
} from "@/features/cameras/api/cameras-api";
import { CameraConnectionInformation } from "@/features/cameras/components/camera-connection-information";
import { CameraDestructiveSection } from "@/features/cameras/components/camera-destructive-section";
import { CameraDetailActions } from "@/features/cameras/components/camera-detail-actions";
import { CameraDetailPlayer } from "@/features/cameras/components/camera-detail-player";
import {
  resolveCameraPreviewSource,
  type CameraPreviewSelection,
} from "@/features/cameras/components/camera-preview-selection";
import { CameraSources } from "@/features/cameras/components/camera-sources";
import { apiClient as defaultApiClient } from "@/lib/api-client";

/** 当前页独立保存开始/停止意图和临时 Source，详情刷新不会覆盖这两类用户选择。 */
function CameraDetailContent({
  camera,
  apiClient,
  firstSource,
}: {
  camera: CameraDetail;
  apiClient: AxiosInstance;
  firstSource: CameraSourceDetail;
}) {
  const [previewRequested, setPreviewRequested] = useState(true);
  const [previewSelection, setPreviewSelection] =
    useState<CameraPreviewSelection>({ kind: "automatic" });
  const preview = resolveCameraPreviewSource(camera, previewSelection);

  if (preview.temporarySelectionLost) {
    // React 允许组件在 render 中根据新 props 调整自己的状态。该分支只会执行一次：下一次 render
    // 已是 automatic，因此不会形成循环，也不会短暂提交已失效的临时 Source。
    setPreviewSelection({ kind: "automatic" });
  }

  return (
    <PageContainer>
      <PageHeader
        title={camera.name}
        description="摄像头连接信息与实时预览"
        actions={
          <CameraDetailActions
            camera={camera}
            apiClient={apiClient}
            available={preview.source !== null}
            previewRequested={previewRequested}
            onPreviewRequestedChange={setPreviewRequested}
          />
        }
        className="sm:items-center"
        actionsClassName="self-end sm:self-auto"
      />
      <div className="grid min-w-0 items-start gap-6 min-[1200px]:grid-cols-[minmax(0,1.65fr)_minmax(18rem,0.75fr)]">
        <CameraDetailPlayer
          sources={camera.sources}
          source={preview.source}
          previewRequested={previewRequested}
          onSourceChange={(sourceId) =>
            setPreviewSelection({ kind: "temporary", sourceId })
          }
        />
        <CameraConnectionInformation
          camera={camera}
          firstSource={firstSource}
        />
      </div>
      <CameraSources camera={camera} apiClient={apiClient} />
      <CameraDestructiveSection />
    </PageContainer>
  );
}

/**
 * Camera 详情组合入口管理按 sort_order 自动选择、预览意图和当前页临时 Source。连接信息、Source
 * 表格、页面 actions 与删除区域各自在相邻组件中维护；默认预览源只影响 Card，不参与详情播放。
 */
export function CameraDetailView({
  camera,
  apiClient = defaultApiClient,
}: {
  camera: CameraDetail;
  apiClient?: AxiosInstance;
}) {
  const firstSource = camera.sources[0];

  if (firstSource === undefined) {
    // Camera 聚合要求至少一路 Source；这里保留防御检查，同时避免把默认源 ID 当作详情可用条件。
    throw new Error("Camera Detail 至少需要一路视频源。");
  }

  // 详情刷新按最新排序重新解析自动 Source；默认源变化不影响详情，且不会覆盖开始/停止意图。
  return (
    <CameraDetailContent
      key={camera.camera_id}
      camera={camera}
      apiClient={apiClient}
      firstSource={firstSource}
    />
  );
}
