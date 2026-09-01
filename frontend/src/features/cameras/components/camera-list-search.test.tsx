import { act, fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import {
  CAMERA_LIST_SEARCH_DEBOUNCE_MS,
  CameraListSearch,
} from "@/features/cameras/components/camera-list-search";

test("输入框左侧显示装饰性搜索图标，防抖 300ms 后提交 trim 查询", () => {
  vi.useFakeTimers();
  const onQueryChange = vi.fn();
  const rendered = render(
    <CameraListSearch query={undefined} onQueryChange={onQueryChange} />,
  );
  const searchbox = screen.getByRole("searchbox", { name: "搜索摄像头" });
  const inputGroup = searchbox.closest("[data-slot='input-group']");
  const iconAddon = inputGroup?.querySelector(
    "[data-slot='input-group-addon']",
  );

  expect(iconAddon).toHaveAttribute("data-align", "inline-start");
  expect(iconAddon).toHaveAttribute("aria-hidden", "true");
  expect(iconAddon?.querySelector("svg")).toBeInTheDocument();

  fireEvent.change(searchbox, {
    target: { value: "  洗手区  " },
  });
  void act(() => vi.advanceTimersByTime(CAMERA_LIST_SEARCH_DEBOUNCE_MS - 1));
  expect(onQueryChange).not.toHaveBeenCalled();

  void act(() => vi.advanceTimersByTime(1));
  expect(onQueryChange).toHaveBeenCalledWith("洗手区");

  rendered.rerender(
    <CameraListSearch query="洗手区" onQueryChange={onQueryChange} />,
  );
  expect(screen.queryByRole("button", { name: "清除搜索" })).toBeNull();
  expect(screen.getByRole("searchbox", { name: "搜索摄像头" })).toHaveValue(
    "洗手区",
  );
});

test("外部 URL 查询变化会取消旧防抖，不让旧输入覆盖新状态", () => {
  vi.useFakeTimers();
  const onQueryChange = vi.fn();
  const rendered = render(
    <CameraListSearch query="旧查询" onQueryChange={onQueryChange} />,
  );

  fireEvent.change(screen.getByRole("searchbox", { name: "搜索摄像头" }), {
    target: { value: "即将过期" },
  });
  rendered.rerender(
    <CameraListSearch query="浏览器恢复" onQueryChange={onQueryChange} />,
  );
  void act(() => vi.advanceTimersByTime(CAMERA_LIST_SEARCH_DEBOUNCE_MS));

  expect(onQueryChange).not.toHaveBeenCalled();
  expect(screen.getByRole("searchbox", { name: "搜索摄像头" })).toHaveValue(
    "浏览器恢复",
  );
});
