import { createFileRoute } from "@tanstack/react-router";

import { PageContainer } from "@/components/layout/page-container";
import { PageHeader } from "@/components/layout/page-header";
import { getLoaderDataLabelOrParam } from "@/lib/route-meta";

export const Route = createFileRoute("/_app/tasks/$taskId")({
  staticData: {
    breadcrumb: {
      label: (match) =>
        getLoaderDataLabelOrParam(match, () => undefined, "taskId") ??
        "检测任务详情",
    },
    back: {
      to: "/tasks",
      label: "返回检测任务列表",
    },
  },
  component: TaskDetailPage,
});

function TaskDetailPage() {
  const { taskId } = Route.useParams();

  return (
    <PageContainer>
      <PageHeader
        title={taskId}
        description="检测任务详情路由已就绪；实体名称将在正式 API 契约接入后加载。"
      />
      <section aria-labelledby="task-detail-route-skeleton-title">
        <h2 id="task-detail-route-skeleton-title" className="font-medium">
          路由骨架
        </h2>
        <p className="text-muted-foreground mt-1 text-sm">
          此处仅用于验证详情层级、Breadcrumb 与返回操作，未实现任务执行、ROI
          或视频功能。
        </p>
      </section>
    </PageContainer>
  );
}
