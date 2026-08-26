import { createRootRoute, RouterProvider } from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { RouteError } from "@/components/route-state/route-error";
import { RoutePending } from "@/components/route-state/route-pending";
import { createTestRouter } from "@/test/render-router";

test("Pending 提供可访问状态并隐藏装饰性 Skeleton", () => {
  render(<RoutePending label="正在加载摄像头内容" variant="card-list" />);

  const status = screen.getByRole("status", {
    name: "正在加载摄像头内容",
  });

  expect(status).toHaveAttribute("aria-busy", "true");
  expect(screen.getByText("正在加载摄像头内容")).toHaveClass("sr-only");
  expect(status.querySelector('[aria-hidden="true"]')).toBeInTheDocument();
  expect(
    status.querySelectorAll('[data-slot="skeleton"].animate-pulse').length,
  ).toBeGreaterThan(0);
  expect(status.querySelectorAll('[data-slot="card"]')).toHaveLength(4);
});

test("Table List Pending 在宽屏保留原型的五列表头", () => {
  render(<RoutePending label="正在加载检测任务" variant="table-list" />);

  const status = screen.getByRole("status", { name: "正在加载检测任务" });
  expect(status.querySelectorAll("th")).toHaveLength(5);
  expect(status.querySelectorAll("tbody tr")).toHaveLength(5);
});

test("Error 重试通过 Router invalidate 重新加载路由", async () => {
  const user = userEvent.setup();
  const rootRoute = createRootRoute({
    component: () => (
      <RouteError
        title="无法加载检测任务内容"
        description="检测任务页面暂时不可用，请稍后重试。"
        returnLinkOptions={{ to: "/tasks" }}
        returnLabel="返回检测任务列表"
      />
    ),
  });
  const router = createTestRouter(
    { routeTree: rootRoute },
    { initialEntries: ["/"] },
  );
  const invalidate = vi.spyOn(router, "invalidate");

  render(<RouterProvider router={router} />);
  await user.click(await screen.findByRole("button", { name: "重试" }));

  expect(invalidate).toHaveBeenCalledTimes(1);
});
