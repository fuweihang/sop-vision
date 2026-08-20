import { createFileRoute } from "@tanstack/react-router";

import { PageContainer } from "@/components/layout/page-container";
import { PageHeader } from "@/components/layout/page-header";
import { getLoaderDataLabelOrParam } from "@/lib/route-meta";

export const Route = createFileRoute("/_app/cameras/$cameraId")({
  staticData: {
    breadcrumb: {
      label: (match) =>
        getLoaderDataLabelOrParam(match, () => undefined, "cameraId") ??
        "摄像头详情",
    },
    back: {
      to: "/cameras",
      label: "返回摄像头列表",
    },
  },
  component: CameraDetailPage,
});

function CameraDetailPage() {
  const { cameraId } = Route.useParams();

  return (
    <PageContainer>
      <PageHeader
        title={cameraId}
        description="摄像头详情路由已就绪；实体名称将在正式 API 契约接入后加载。"
      />
      <section aria-labelledby="camera-detail-route-skeleton-title">
        <h2 id="camera-detail-route-skeleton-title" className="font-medium">
          路由骨架
        </h2>
        <p className="text-muted-foreground mt-1 text-sm">
          此处仅用于验证详情层级、Breadcrumb
          与返回操作，未实现视频、来源或编辑功能。
        </p>
      </section>
    </PageContainer>
  );
}
