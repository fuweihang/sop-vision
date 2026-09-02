import { AlertCircleIcon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { useState } from "react";
import type { AxiosInstance } from "axios";

import { PageContainer } from "@/components/layout/page-container";
import { PageHeader } from "@/components/layout/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import type {
  CameraDetail,
  CameraSourceDetail,
} from "@/features/cameras/api/cameras-api";
import { CameraConnectionInformation } from "@/features/cameras/components/camera-connection-information";
import { CameraDestructiveSection } from "@/features/cameras/components/camera-destructive-section";
import { CameraDetailActions } from "@/features/cameras/components/camera-detail-actions";
import { CameraDetailPlayer } from "@/features/cameras/components/camera-detail-player";
import {
  findCameraDefaultSource,
  resolveCameraPreviewSource,
  type CameraPreviewSelection,
} from "@/features/cameras/components/camera-preview-selection";
import { CameraSources } from "@/features/cameras/components/camera-sources";
import { apiClient as defaultApiClient } from "@/lib/api-client";

/** 当前页独立保存开始/停止意图和临时 Source，详情刷新不会覆盖这两类用户选择。 */
function CameraDetailContent({
  camera,
  apiClient,
  defaultSource,
}: {
  camera: CameraDetail;
  apiClient: AxiosInstance;
  defaultSource: CameraSourceDetail;
}) {
  const [previewRequested, setPreviewRequested] = useState(true);
  const [previewSelection, setPreviewSelection] =
    useState<CameraPreviewSelection>({ kind: "default" });
  const preview = resolveCameraPreviewSource(
    camera,
    defaultSource,
    previewSelection,
  );

  if (preview.temporarySelectionLost) {
    // React 允许组件在 render 中根据新 props 调整自己的状态。该分支只会执行一次：下一次 render
    // 已是 default，因此不会形成循环，也不会短暂提交已失效的临时 Source。
    setPreviewSelection({ kind: "default" });
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
          defaultSource={defaultSource}
        />
      </div>
      <CameraSources camera={camera} apiClient={apiClient} />
      <CameraDestructiveSection />
    </PageContainer>
  );
}

/**
 * Camera 详情组合入口管理默认 Source 校验、预览意图和当前页临时 Source。连接信息、Source 表格、
 * 页面 actions 与删除区域各自在相邻组件中维护。
 */
export function CameraDetailView({
  camera,
  apiClient = defaultApiClient,
}: {
  camera: CameraDetail;
  apiClient?: AxiosInstance;
}) {
  const defaultSource = findCameraDefaultSource(camera);

  if (defaultSource === undefined) {
    // Backend 聚合和 Schema 正常情况下不会触发；防御分支避免损坏响应静默显示错误默认源。
    return (
      <PageContainer>
        <PageHeader
          title={camera.name}
          description="摄像头详情暂时无法完整显示。"
        />
        <Alert variant="destructive" className="max-w-2xl">
          <HugeiconsIcon icon={AlertCircleIcon} strokeWidth={2} />
          <AlertTitle>默认预览源无效</AlertTitle>
          <AlertDescription>
            当前详情没有匹配的默认预览源，请稍后重试。
          </AlertDescription>
        </Alert>
      </PageContainer>
    );
  }

  // 详情刷新和 Backend 默认源变化都只重新解析实际 Source，不覆盖用户开始/停止预览的选择。
  return (
    <CameraDetailContent
      key={camera.camera_id}
      camera={camera}
      apiClient={apiClient}
      defaultSource={defaultSource}
    />
  );
}
