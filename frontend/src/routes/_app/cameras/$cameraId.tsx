import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link, notFound } from "@tanstack/react-router";

import { RouteNotFound } from "@/components/route-state/route-not-found";
import { RoutePending } from "@/components/route-state/route-pending";
import { cameraDetailQueryOptions } from "@/features/cameras/api/camera-detail-query";
import { CameraDetailView } from "@/features/cameras/components/camera-detail-view";
import { ApiProblemError } from "@/lib/api-errors";
import {
  getLoaderDataLabelOrParam,
  type ShellLinkPresentationProps,
} from "@/lib/route-meta";

function selectCameraName(loaderData: unknown) {
  return typeof loaderData === "object" &&
    loaderData !== null &&
    "name" in loaderData &&
    typeof loaderData.name === "string"
    ? loaderData.name
    : undefined;
}

function isCameraNotFound(error: unknown) {
  return (
    error instanceof ApiProblemError &&
    error.problem.status === 404 &&
    error.problem.code === "CAMERA_NOT_FOUND"
  );
}

export const Route = createFileRoute("/_app/cameras/$cameraId")({
  staticData: {
    breadcrumb: {
      label: (match) =>
        getLoaderDataLabelOrParam(match, selectCameraName, "cameraId") ??
        "摄像头详情",
    },
    back: {
      label: "返回摄像头列表",
      renderLink: (props) => <CameraDetailBackLink {...props} />,
    },
  },
  loader: async ({ context, params }) => {
    try {
      const camera = await context.queryClient.ensureQueryData(
        cameraDetailQueryOptions(params.cameraId, context.apiClient),
      );
      // 完整 CameraDetail 只保留在 Query 内存缓存；Router 只保存 Breadcrumb 所需名称。
      return { name: camera.name };
    } catch (error: unknown) {
      if (isCameraNotFound(error)) {
        notFound({ throw: true });
      }
      throw error;
    }
  },
  component: CameraDetailPage,
  pendingComponent: CameraDetailPending,
  notFoundComponent: CameraNotFound,
});

function CameraDetailPending() {
  return <RoutePending label="正在加载摄像头详情" variant="detail" />;
}

function CameraDetailBackLink(props: ShellLinkPresentationProps) {
  const search = Route.useSearch();

  return <Link to="/cameras" search={search} preload="intent" {...props} />;
}

function CameraDetailPage() {
  const { cameraId } = Route.useParams();
  const { apiClient } = Route.useRouteContext();
  const { data: camera } = useSuspenseQuery(
    cameraDetailQueryOptions(cameraId, apiClient),
  );

  return <CameraDetailView camera={camera} apiClient={apiClient} />;
}

function CameraNotFound() {
  const search = Route.useSearch();

  return (
    <RouteNotFound
      kind="camera"
      title="未找到摄像头"
      description="该摄像头不存在或已被删除。"
      returnLinkOptions={{ to: "/cameras", search }}
      returnLabel="返回摄像头列表"
    />
  );
}
