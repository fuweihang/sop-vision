import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { RoutePending } from "@/components/route-state/route-pending";

test("Pending 提供可访问状态并隐藏装饰性 Skeleton", () => {
  render(<RoutePending label="正在加载摄像头内容" variant="card-list" />);

  const status = screen.getByRole("status", {
    name: "正在加载摄像头内容",
  });

  expect(status).toHaveAttribute("aria-busy", "true");
  expect(status.querySelector('[aria-hidden="true"]')).toBeInTheDocument();
  expect(status.querySelectorAll('[data-slot="card"]')).toHaveLength(4);
});

test("Table List Pending 在宽屏保留原型的五列表头", () => {
  render(<RoutePending label="正在加载检测任务" variant="table-list" />);

  const status = screen.getByRole("status", { name: "正在加载检测任务" });
  expect(status.querySelectorAll("th")).toHaveLength(5);
  expect(status.querySelectorAll("tbody tr")).toHaveLength(5);
});
