import { Camera01Icon, Search01Icon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import {
  useQueryErrorResetBoundary,
  useSuspenseQuery,
} from "@tanstack/react-query";
import {
  createFileRoute,
  useNavigate,
  useRouter,
} from "@tanstack/react-router";
import { useCallback, useState } from "react";

import { PageContainer } from "@/components/layout/page-container";
import {
  PageBackgroundStatus,
  PageEmptyState,
  PageRecoverableError,
} from "@/components/page-state/page-state";
import { RoutePending } from "@/components/route-state/route-pending";
import { Button } from "@/components/ui/button";
import { cameraListQueryOptions } from "@/features/cameras/api/camera-list-query";
import { CameraCreateDialog } from "@/features/cameras/components/camera-create-dialog";
import { CameraListCard } from "@/features/cameras/components/camera-list-card";
import {
  CameraListPagination,
  CameraOutOfRangeActions,
} from "@/features/cameras/components/camera-list-pagination";
import { cameraPageCount } from "@/features/cameras/components/camera-list-pagination-model";
import { CameraListSearch } from "@/features/cameras/components/camera-list-search";

export const Route = createFileRoute("/_app/cameras/")({
  loaderDeps: ({ search: { q, page, page_size } }) => ({
    q,
    page,
    page_size,
  }),
  loader: async ({ context, deps }) => {
    await context.queryClient.ensureQueryData(
      cameraListQueryOptions(deps, context.apiClient),
    );
    // 列表数据只由 TanStack Query 保存；Router loader 只负责进入页面前填充 Query cache。
  },
  component: CamerasPage,
  pendingComponent: CamerasListPending,
  errorComponent: CamerasListError,
});

function CamerasListPending() {
  return <RoutePending label="正在加载摄像头列表" variant="card-list" />;
}

function CamerasListError() {
  const router = useRouter();
  const { reset: resetQueryError } = useQueryErrorResetBoundary();
  const [isRetrying, setIsRetrying] = useState(false);

  async function retry() {
    setIsRetrying(true);
    // Query 的错误状态必须先清除，否则重新执行 loader 时仍可能立即读到旧错误。
    resetQueryError();
    try {
      await router.invalidate();
    } finally {
      setIsRetrying(false);
    }
  }

  return (
    <PageContainer>
      <PageRecoverableError
        title="无法加载摄像头列表"
        description="当前没有可显示的列表数据，请检查网络或服务状态后重试。"
        onRetry={() => void retry()}
        isRetrying={isRetrying}
      />
    </PageContainer>
  );
}

function CamerasPage() {
  const search = Route.useSearch();
  const { apiClient } = Route.useRouteContext();
  const navigate = useNavigate({ from: Route.fullPath });
  const query = useSuspenseQuery(cameraListQueryOptions(search, apiClient));
  const cameraPage = query.data;

  const updateQuery = useCallback(
    (nextQuery: string | undefined) => {
      void navigate({
        to: "/cameras",
        search: (previous) => ({
          ...previous,
          q: nextQuery,
          page: 1,
        }),
        replace: true,
      });
    },
    [navigate],
  );

  // 后台轮询期间继续显示已有 Cards，且不插入临时状态行；否则每 15 秒一次的提示会把 Grid
  // 向下推开，造成列表周期性跳动。失败仍显示非阻塞提示，便于用户发现数据可能已过期并重试。
  const backgroundStatus = query.isRefetchError
    ? {
        state: "error" as const,
        title: "摄像头列表刷新失败",
        description: "已保留上一次成功加载的列表，你可以继续浏览或重新刷新。",
        onRetry: () => void query.refetch(),
      }
    : { state: "idle" as const };

  const totalPages = cameraPageCount(cameraPage.total, cameraPage.page_size);
  const isOutOfRange = cameraPage.total > 0 && cameraPage.items.length === 0;

  return (
    <PageContainer>
      <div
        role="group"
        aria-label="摄像头列表工具栏"
        className="flex min-w-0 items-center gap-3"
      >
        <CameraListSearch query={search.q} onQueryChange={updateQuery} />
        <div className="shrink-0">
          <CameraCreateDialog apiClient={apiClient} />
        </div>
      </div>
      <PageBackgroundStatus {...backgroundStatus} />

      {cameraPage.total === 0 && search.q === undefined ? (
        <PageEmptyState
          kind="empty"
          title="尚无摄像头"
          description="添加第一台摄像头后，就可以在这里查看连接和视频源状态。"
          media={<HugeiconsIcon icon={Camera01Icon} strokeWidth={2} />}
          action={<CameraCreateDialog apiClient={apiClient} />}
        />
      ) : cameraPage.total === 0 ? (
        <PageEmptyState
          kind="no-results"
          title="未找到匹配摄像头"
          description={`没有名称或 IPv4 匹配“${search.q}”的摄像头。`}
          media={<HugeiconsIcon icon={Search01Icon} strokeWidth={2} />}
          action={
            <Button
              type="button"
              variant="outline"
              onClick={() => updateQuery(undefined)}
            >
              清除搜索
            </Button>
          }
        />
      ) : isOutOfRange ? (
        <PageEmptyState
          kind="out-of-range"
          title="当前页没有摄像头"
          description={`当前是第 ${cameraPage.page} 页，共 ${totalPages} 页。列表数据可能已发生变化，请选择返回。`}
          media={<HugeiconsIcon icon={Camera01Icon} strokeWidth={2} />}
          action={<CameraOutOfRangeActions page={cameraPage} search={search} />}
        />
      ) : (
        <>
          <section aria-label="摄像头列表">
            <div className="grid min-w-0 gap-4 min-[520px]:grid-cols-2 min-[1200px]:grid-cols-4">
              {cameraPage.items.map((camera) => (
                <CameraListCard
                  key={camera.camera_id}
                  camera={camera}
                  search={search}
                />
              ))}
            </div>
          </section>
          <CameraListPagination page={cameraPage} search={search} />
        </>
      )}
    </PageContainer>
  );
}
