import { createFileRoute } from "@tanstack/react-router";

import { CameraCreateDialog } from "@/features/cameras/components/camera-create-dialog";
import { PageContainer } from "@/components/layout/page-container";
import { PageHeader } from "@/components/layout/page-header";
import { RoutePending } from "@/components/route-state/route-pending";

export const Route = createFileRoute("/_app/cameras/")({
  component: CamerasPage,
  pendingComponent: CamerasListPending,
});

function CamerasListPending() {
  return <RoutePending label="正在加载摄像头列表" variant="card-list" />;
}

function CamerasPage() {
  const { apiClient } = Route.useRouteContext();

  return (
    <PageContainer>
      <PageHeader
        title="摄像头"
        description="管理摄像头连接信息和视频源配置。"
        actions={<CameraCreateDialog apiClient={apiClient} />}
      />
      <section aria-labelledby="cameras-route-skeleton-title">
        <h2 id="cameras-route-skeleton-title" className="font-medium">
          路由骨架
        </h2>
        <p className="text-muted-foreground mt-1 text-sm">
          摄像头列表数据仍为占位；创建和详情已可用，编辑与删除尚未实现。
        </p>
      </section>
    </PageContainer>
  );
}
