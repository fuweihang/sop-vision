import { createFileRoute } from "@tanstack/react-router";

import { PageContainer } from "@/components/layout/page-container";
import { PageHeader } from "@/components/layout/page-header";
import { RoutePending } from "@/components/route-state/route-pending";

export const Route = createFileRoute("/_app/tasks/")({
  component: TasksPage,
  pendingComponent: TasksListPending,
});

function TasksListPending() {
  return <RoutePending label="正在加载检测任务列表" variant="task-list" />;
}

function TasksPage() {
  return (
    <PageContainer>
      <PageHeader
        title="检测任务"
        description="检测任务列表路由与页面布局已就绪。"
      />
      <section aria-labelledby="tasks-route-skeleton-title">
        <h2 id="tasks-route-skeleton-title" className="font-medium">
          路由骨架
        </h2>
        <p className="text-muted-foreground mt-1 text-sm">
          此处仅用于验证应用 Shell；任务列表与执行能力尚未实现。
        </p>
      </section>
    </PageContainer>
  );
}
