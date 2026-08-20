import type { QueryClient } from "@tanstack/react-query";
import {
  createRootRouteWithContext,
  Outlet,
  useRouter,
  type ErrorComponentProps,
} from "@tanstack/react-router";
import type { AxiosInstance } from "axios";

import { RouteError } from "@/components/route-state/route-error";
import { RouteNotFound } from "@/components/route-state/route-not-found";

export interface RouterContext {
  apiClient: AxiosInstance;
  queryClient: QueryClient;
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: RootLayout,
  errorComponent: RootRouteError,
  notFoundComponent: RootRouteNotFound,
});

function RootLayout() {
  return <Outlet />;
}

function RootRouteError({ reset }: ErrorComponentProps) {
  const router = useRouter();

  return (
    <RouteError
      title="应用暂时无法显示"
      description="应用遇到意外问题，当前页面未能完成加载。"
      onRetry={() => router.invalidate()}
      reset={reset}
      returnTo="/"
      returnLabel="返回首页"
    />
  );
}

function RootRouteNotFound() {
  return (
    <RouteNotFound
      kind="page"
      title="页面不存在"
      description="当前地址没有对应的页面，请返回首页继续浏览。"
      returnTo="/"
      returnLabel="返回首页"
    />
  );
}
