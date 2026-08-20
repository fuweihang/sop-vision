import {
  createFileRoute,
  Outlet,
  useLocation,
  useRouter,
  type ErrorComponentProps,
} from "@tanstack/react-router";

import { RouteError } from "@/components/route-state/route-error";
import { RouteNotFound } from "@/components/route-state/route-not-found";
import { RoutePending } from "@/components/route-state/route-pending";

export const Route = createFileRoute("/_app/tasks")({
  staticData: {
    breadcrumb: "检测任务",
  },
  component: TasksLayout,
  pendingComponent: TasksRoutePending,
  errorComponent: TasksRouteError,
  notFoundComponent: TasksRouteNotFound,
});

function TasksLayout() {
  return <Outlet />;
}

function TasksRoutePending() {
  const pathname = useLocation({ select: (location) => location.pathname });
  const isDetail = pathname.split("/").filter(Boolean).length > 1;

  return (
    <RoutePending
      label="正在加载检测任务内容"
      variant={isDetail ? "detail" : "task-list"}
    />
  );
}

function TasksRouteError({ reset }: ErrorComponentProps) {
  const router = useRouter();

  return (
    <RouteError
      title="无法加载检测任务内容"
      description="检测任务页面暂时不可用，请稍后重试。"
      onRetry={() => router.invalidate()}
      reset={reset}
      returnTo="/tasks"
      returnLabel="返回检测任务列表"
    />
  );
}

function TasksRouteNotFound() {
  return (
    <RouteNotFound
      kind="task"
      title="未找到检测任务"
      description="该检测任务不存在、已被删除，或当前地址无效。"
      returnTo="/tasks"
      returnLabel="返回检测任务列表"
    />
  );
}
