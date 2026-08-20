import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/tasks")({
  staticData: {
    breadcrumb: "检测任务",
  },
  component: TasksPage,
});

function TasksPage() {
  return (
    <section aria-labelledby="tasks-title">
      <h1 id="tasks-title">检测任务</h1>
      <p>检测任务管理功能将在此提供。</p>
    </section>
  );
}
