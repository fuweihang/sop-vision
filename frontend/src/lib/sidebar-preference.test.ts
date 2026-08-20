import { describe, expect, test } from "vitest";

import { parseSidebarDefaultOpen } from "@/lib/sidebar-preference";

describe("解析 Sidebar 默认展开偏好", () => {
  test("使用值为 true 的 cookie", () => {
    expect(parseSidebarDefaultOpen("theme=dark; sidebar_state=true")).toBe(
      true,
    );
  });

  test("使用值为 false 的 cookie", () => {
    expect(parseSidebarDefaultOpen("sidebar_state=false; theme=light")).toBe(
      false,
    );
  });

  test("cookie 缺失时默认展开", () => {
    expect(parseSidebarDefaultOpen("theme=dark")).toBe(true);
  });

  test("cookie 值非法时默认展开", () => {
    expect(parseSidebarDefaultOpen("sidebar_state=collapsed")).toBe(true);
  });
});
