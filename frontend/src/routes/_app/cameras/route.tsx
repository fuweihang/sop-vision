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

export const Route = createFileRoute("/_app/cameras")({
  staticData: {
    breadcrumb: "摄像头",
  },
  component: CamerasLayout,
  pendingComponent: CamerasRoutePending,
  errorComponent: CamerasRouteError,
  notFoundComponent: CamerasRouteNotFound,
});

function CamerasLayout() {
  return <Outlet />;
}

function CamerasRoutePending() {
  const pathname = useLocation({ select: (location) => location.pathname });
  const isDetail = pathname.split("/").filter(Boolean).length > 1;

  return (
    <RoutePending
      label="正在加载摄像头内容"
      variant={isDetail ? "detail" : "camera-list"}
    />
  );
}

function CamerasRouteError({ reset }: ErrorComponentProps) {
  const router = useRouter();

  return (
    <RouteError
      title="无法加载摄像头内容"
      description="摄像头页面暂时不可用，请稍后重试。"
      onRetry={() => router.invalidate()}
      reset={reset}
      returnTo="/cameras"
      returnLabel="返回摄像头列表"
    />
  );
}

function CamerasRouteNotFound() {
  return (
    <RouteNotFound
      kind="camera"
      title="未找到摄像头"
      description="该摄像头不存在、已被删除，或当前地址无效。"
      returnTo="/cameras"
      returnLabel="返回摄像头列表"
    />
  );
}
