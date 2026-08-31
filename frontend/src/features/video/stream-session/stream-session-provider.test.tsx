import { act, render } from "@testing-library/react";
import { StrictMode } from "react";
import { expect, test, vi } from "vitest";

import { StreamSessionManager } from "@/features/video/stream-session/stream-session-manager";
import { StreamSessionProvider } from "@/features/video/stream-session/stream-session-provider";
import { FakeStreamSession } from "@/features/video/testing/fakes";

test("Strict Mode 紧邻 cleanup/remount 不关闭注入的 Manager", async () => {
  vi.useFakeTimers();
  const manager = new StreamSessionManager(() => new FakeStreamSession());
  const close = vi.spyOn(manager, "close");

  const rendered = render(
    <StrictMode>
      <StreamSessionProvider manager={manager}>
        <span>播放器消费者</span>
      </StreamSessionProvider>
    </StrictMode>,
  );

  await act(() => vi.runOnlyPendingTimersAsync());
  expect(close).not.toHaveBeenCalled();

  rendered.unmount();
  await act(() => vi.runOnlyPendingTimersAsync());
  expect(close).toHaveBeenCalledOnce();
});

test("真实卸载后关闭 Provider 拥有的注入 Manager 和活动 Session", async () => {
  vi.useFakeTimers();
  const session = new FakeStreamSession();
  const manager = new StreamSessionManager(() => session);
  manager.acquire("source-1", "https://media/live/whep");

  const rendered = render(
    <StreamSessionProvider manager={manager}>
      <span>播放器消费者</span>
    </StreamSessionProvider>,
  );
  rendered.unmount();

  expect(session.closeCount).toBe(0);
  await act(() => vi.runOnlyPendingTimersAsync());
  expect(session.closeCount).toBe(1);
  expect(manager.activeSessionCount).toBe(0);
  expect(() => manager.acquire("source-2", "https://media/other/whep")).toThrow(
    "StreamSessionManager 已关闭，不能继续创建播放会话。",
  );
});
