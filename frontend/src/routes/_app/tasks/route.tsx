import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/tasks")({
  staticData: {
    breadcrumb: "检测任务",
  },
  component: TasksLayout,
});

function TasksLayout() {
  return <Outlet />;
}
