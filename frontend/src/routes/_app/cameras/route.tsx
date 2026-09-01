import { createFileRoute, Outlet } from "@tanstack/react-router";
import { Link } from "@tanstack/react-router";
import { z } from "zod";

import { RouteError } from "@/components/route-state/route-error";
import { RouteNotFound } from "@/components/route-state/route-not-found";
import { initialCameraListPageSize } from "@/features/cameras/components/camera-list-page-size";
import type { ShellLinkPresentationProps } from "@/lib/route-meta";

const cameraSearchQuerySchema = z
  .preprocess((value) => {
    if (typeof value !== "string") {
      return value;
    }

    const trimmedValue = value.trim();
    return trimmedValue === "" ? undefined : trimmedValue;
  }, z.string().max(100).optional())
  .catch(undefined);

function numericSearchParam(value: unknown) {
  return typeof value === "string" && value.trim() !== ""
    ? Number(value)
    : value;
}

/**
 * Cameras 父路由统一规范化列表查询参数，使详情 URL 也能携带同一份返回上下文。
 * 非法值恢复成 Backend 默认值，不把未经校验的字符串继续传给 Query Key 或 HTTP Client。
 */
export const cameraListSearchSchema = z
  .object({
    q: cameraSearchQuerySchema,
    page: z
      .preprocess(numericSearchParam, z.number().int().min(1))
      .catch(1)
      .default(1),
    page_size: z
      .preprocess(numericSearchParam, z.number().int().min(1).max(100))
      .catch(20)
      // 函数默认值只处理 URL 缺失；显式非法值仍由 catch 恢复为 Backend 默认的 20。
      .default(initialCameraListPageSize),
  })
  .transform(({ q, page, page_size }) => ({ q, page, page_size }));

export const Route = createFileRoute("/_app/cameras")({
  validateSearch: cameraListSearchSchema,
  staticData: {
    breadcrumb: {
      label: "摄像头",
      renderLink: (props) => <CamerasListLink {...props} />,
    },
  },
  component: CamerasLayout,
  errorComponent: CamerasRouteError,
  notFoundComponent: CamerasRouteNotFound,
});

function CamerasLayout() {
  return <Outlet />;
}

function CamerasListLink(props: ShellLinkPresentationProps) {
  const search = Route.useSearch();

  return <Link to="/cameras" search={search} preload="intent" {...props} />;
}

function CamerasRouteError() {
  const search = Route.useSearch();

  return (
    <RouteError
      title="无法加载摄像头内容"
      description="摄像头页面暂时不可用，请稍后重试。"
      returnLinkOptions={{ to: "/cameras", search }}
      returnLabel="返回摄像头列表"
    />
  );
}

function CamerasRouteNotFound() {
  const search = Route.useSearch();

  return (
    <RouteNotFound
      kind="camera"
      title="未找到摄像头"
      description="该摄像头不存在、已被删除，或当前地址无效。"
      returnLinkOptions={{ to: "/cameras", search }}
      returnLabel="返回摄像头列表"
    />
  );
}
