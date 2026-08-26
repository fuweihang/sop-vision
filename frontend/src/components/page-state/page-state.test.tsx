import { Search01Icon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import {
  PageBackgroundStatus,
  PageEmptyState,
  PageRecoverableError,
} from "@/components/page-state/page-state";
import { Button } from "@/components/ui/button";

test("空数据与搜索无结果保留不同页面状态和调用方动作", () => {
  const { rerender } = render(
    <PageEmptyState
      kind="empty"
      title="尚无资源"
      description="创建第一个资源后会显示在这里。"
      media={<HugeiconsIcon icon={Search01Icon} strokeWidth={2} />}
      action={<Button>创建资源</Button>}
    />,
  );

  expect(
    screen.getByText("尚无资源").closest("[data-page-state]"),
  ).toHaveAttribute("data-page-state", "empty");
  expect(screen.getByRole("button", { name: "创建资源" })).toBeVisible();

  rerender(
    <PageEmptyState
      kind="no-results"
      title="没有匹配结果"
      description="调整搜索条件后重试。"
      media={<HugeiconsIcon icon={Search01Icon} strokeWidth={2} />}
      action={<Button variant="outline">清除搜索</Button>}
    />,
  );

  expect(
    screen.getByText("没有匹配结果").closest("[data-page-state]"),
  ).toHaveAttribute("data-page-state", "no-results");
  expect(screen.getByRole("button", { name: "清除搜索" })).toBeVisible();
});

test("首次失败允许重试且重试中阻止重复操作", async () => {
  const user = userEvent.setup();
  const retry = vi.fn();
  const { rerender } = render(
    <PageRecoverableError
      title="首次加载失败"
      description="当前没有可显示的数据。"
      onRetry={retry}
    />,
  );

  await user.click(screen.getByRole("button", { name: "重试" }));
  expect(retry).toHaveBeenCalledTimes(1);

  rerender(
    <PageRecoverableError
      title="首次加载失败"
      description="当前没有可显示的数据。"
      onRetry={retry}
      isRetrying
    />,
  );
  expect(screen.getByRole("button", { name: "正在重试" })).toBeDisabled();
});

test("后台刷新和失败提供非阻塞、可恢复反馈", async () => {
  const user = userEvent.setup();
  const retry = vi.fn();
  const { rerender } = render(
    <PageBackgroundStatus state="refreshing" label="正在刷新最新数据" />,
  );

  expect(
    screen.getByRole("status", { name: "正在刷新最新数据" }),
  ).toBeVisible();

  rerender(
    <PageBackgroundStatus
      state="error"
      title="刷新失败"
      description="已保留上一次成功加载的内容。"
      onRetry={retry}
    />,
  );
  await user.click(screen.getByRole("button", { name: "重新刷新" }));
  expect(retry).toHaveBeenCalledTimes(1);
});
