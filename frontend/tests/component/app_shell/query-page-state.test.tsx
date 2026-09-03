import {
  QueryClient,
  QueryClientProvider,
  useQuery,
} from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { type PropsWithChildren } from "react";
import { expect, test } from "vitest";

import {
  PageBackgroundStatus,
  PageRecoverableError,
} from "@/components/page-state/page-state";
import { RoutePending } from "@/components/route-state/route-pending";
import { Button } from "@/components/ui/button";
import { cameraQueryKeys } from "@/features/cameras/api/camera-query-keys";
import { listCameras } from "@/features/cameras/api/cameras-api";
import { createCamerasMswScenario } from "@/mocks/cameras/scenarios";
import { mockServer } from "@/mocks/node";

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
    },
  });
}

function CameraListStateHarness() {
  const query = useQuery({
    queryKey: cameraQueryKeys.cameras(),
    queryFn: () => listCameras(),
  });

  if (query.isPending) {
    return <RoutePending label="正在加载测试列表" variant="card-list" />;
  }

  if (query.isLoadingError) {
    return (
      <PageRecoverableError
        title="首次加载失败"
        description="当前没有可显示的数据。"
        onRetry={() => void query.refetch()}
        isRetrying={query.isFetching}
      />
    );
  }

  return (
    <section aria-label="测试列表内容">
      <Button type="button" onClick={() => void query.refetch()}>
        触发刷新
      </Button>
      {query.data?.items.map((camera) => (
        <p key={camera.camera_id}>{camera.name}</p>
      ))}
      <PageBackgroundStatus
        {...(query.isFetching
          ? { state: "refreshing", label: "正在刷新测试列表" }
          : query.isRefetchError
            ? {
                state: "error",
                title: "后台刷新失败",
                description: "已保留上一次成功加载的内容。",
                onRetry: () => void query.refetch(),
              }
            : { state: "idle" })}
      />
    </section>
  );
}

function QueryHarnessProvider({ children }: PropsWithChildren) {
  return (
    <QueryClientProvider client={createTestQueryClient()}>
      {children}
    </QueryClientProvider>
  );
}

test("首次失败显示完整错误并能重试恢复", async () => {
  const user = userEvent.setup();
  mockServer.use(...createCamerasMswScenario("initial-failure"));
  render(<CameraListStateHarness />, { wrapper: QueryHarnessProvider });

  expect(
    screen.getByRole("status", { name: "正在加载测试列表" }),
  ).toBeVisible();
  expect(await screen.findByText("首次加载失败")).toBeVisible();

  await user.click(screen.getByRole("button", { name: "重试" }));
  expect(await screen.findByText("洗手区 01")).toBeVisible();
});

test("后台刷新失败保留旧内容并提供非阻塞恢复动作", async () => {
  const user = userEvent.setup();
  mockServer.use(...createCamerasMswScenario("background-refresh-failure"));
  render(<CameraListStateHarness />, { wrapper: QueryHarnessProvider });

  expect(await screen.findByText("洗手区 01")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "触发刷新" }));

  expect(await screen.findByText("后台刷新失败")).toBeVisible();
  expect(screen.getByText("洗手区 01")).toBeVisible();
  expect(screen.getByRole("button", { name: "重新刷新" })).toBeVisible();
});
