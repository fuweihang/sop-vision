import { act, fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { useVideoControlsVisibility } from "@/features/video/components/video-controls/controls-visibility-context";
import {
  VideoControlsBar,
  VideoControlsRoot,
} from "@/features/video/components/video-controls/controls-visibility";

function FloatingLayerProbe() {
  const {
    actions: { setFloatingLayerOpen },
  } = useVideoControlsVisibility();

  return (
    <>
      <button
        type="button"
        onClick={() => setFloatingLayerOpen("test-layer", true)}
      >
        打开浮层
      </button>
      <button
        type="button"
        onClick={() => setFloatingLayerOpen("test-layer", false)}
      >
        关闭浮层
      </button>
    </>
  );
}

function renderVisibility() {
  return render(
    <VideoControlsRoot>
      <p>常驻反馈</p>
      <VideoControlsBar>操作栏</VideoControlsBar>
      <FloatingLayerProbe />
    </VideoControlsRoot>,
  );
}

test("鼠标无活动后只隐藏操作栏，常驻反馈保持可见", () => {
  vi.useFakeTimers();
  try {
    renderVisibility();
    const layer = screen.getByRole("group", {
      name: "视频播放器控制层",
    });
    const controls = screen.getByRole("toolbar", { name: "视频操作" });

    fireEvent.pointerMove(layer, { pointerType: "mouse" });
    expect(controls).toHaveClass("opacity-100");
    void act(() => vi.advanceTimersByTime(2_500));
    expect(controls).toHaveClass("opacity-0", "pointer-events-none");
    expect(screen.getByText("常驻反馈")).toBeVisible();
  } finally {
    vi.useRealTimers();
  }
});

test("浮层打开期间保持操作栏，关闭后重新开始隐藏计时", () => {
  vi.useFakeTimers();
  try {
    renderVisibility();
    const controls = screen.getByRole("toolbar", { name: "视频操作" });

    fireEvent.click(screen.getByRole("button", { name: "打开浮层" }));
    void act(() => vi.advanceTimersByTime(2_500));
    expect(controls).toHaveClass("opacity-100");

    fireEvent.click(screen.getByRole("button", { name: "关闭浮层" }));
    void act(() => vi.advanceTimersByTime(2_500));
    expect(controls).toHaveClass("opacity-0", "pointer-events-none");
  } finally {
    vi.useRealTimers();
  }
});
