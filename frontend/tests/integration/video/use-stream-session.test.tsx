import { act, renderHook } from "@testing-library/react";
import { type PropsWithChildren, StrictMode } from "react";
import { expect, test } from "vitest";

import { StreamSessionManagerContext } from "@/features/video/stream-session/stream-session-manager-context";
import { StreamSessionManager } from "@/features/video/stream-session/stream-session-manager";
import { useStreamSession } from "@/features/video/stream-session/use-stream-session";
import { FakeStreamSession } from "../../support/video/fake-stream-session";

function createManagerFixture() {
  const sessions: FakeStreamSession[] = [];
  const manager = new StreamSessionManager(() => {
    const session = new FakeStreamSession();
    sessions.push(session);
    return session;
  });
  return { manager, sessions };
}

function createWrapper(manager: StreamSessionManager, strict = false) {
  return function StreamSessionTestWrapper({ children }: PropsWithChildren) {
    const content = (
      <StreamSessionManagerContext value={manager}>
        {children}
      </StreamSessionManagerContext>
    );
    return strict ? <StrictMode>{content}</StrictMode> : content;
  };
}

test("Strict Mode 复用紧邻重挂载的 Lease，真实卸载后完成释放", async () => {
  const { manager, sessions } = createManagerFixture();
  const rendered = renderHook(
    () => useStreamSession("source-1", "https://media/live/whep"),
    { wrapper: createWrapper(manager, true) },
  );

  await act(() => Promise.resolve());
  expect(sessions).toHaveLength(1);
  expect(manager.activeSessionCount).toBe(1);
  expect(sessions[0]?.closeCount).toBe(0);

  rendered.unmount();
  await act(() => Promise.resolve());
  expect(manager.activeSessionCount).toBe(0);
  expect(sessions[0]?.closeCount).toBe(1);
});

test("source 和 URL 变化时释放旧 Lease，并使用最新 Session 快照", async () => {
  const { manager, sessions } = createManagerFixture();
  const rendered = renderHook(
    ({ sourceId, whepUrl }) => useStreamSession(sourceId, whepUrl),
    {
      wrapper: createWrapper(manager),
      initialProps: {
        sourceId: "source-1",
        whepUrl: "https://media/old/whep",
      },
    },
  );
  expect(sessions).toHaveLength(1);

  act(() => {
    sessions[0]?.emit({ status: "playing", stream: null });
  });
  expect(rendered.result.current.status).toBe("playing");
  act(() => rendered.result.current.reconnect());
  expect(sessions[0]?.reconnectCount).toBe(1);

  rendered.rerender({
    sourceId: "source-1",
    whepUrl: "https://media/new/whep",
  });
  await act(() => Promise.resolve());
  expect(sessions).toHaveLength(2);
  expect(sessions[0]?.closeCount).toBe(1);
  expect(manager.activeSessionCount).toBe(1);

  rendered.rerender({
    sourceId: "source-2",
    whepUrl: "https://media/second/whep",
  });
  await act(() => Promise.resolve());
  expect(sessions).toHaveLength(3);
  expect(sessions[1]?.closeCount).toBe(1);
  expect(manager.activeSessionCount).toBe(1);

  rendered.unmount();
  await act(() => Promise.resolve());
  expect(sessions[2]?.closeCount).toBe(1);
  expect(manager.activeSessionCount).toBe(0);
});

test("sourceId 或 whepUrl 缺失时保持 idle 且不 acquire", async () => {
  const { manager, sessions } = createManagerFixture();
  const rendered = renderHook(
    ({ sourceId, whepUrl }) => useStreamSession(sourceId, whepUrl),
    {
      wrapper: createWrapper(manager),
      initialProps: {
        sourceId: null as string | null,
        whepUrl: null as string | null,
      },
    },
  );

  expect(rendered.result.current.status).toBe("idle");
  expect(sessions).toHaveLength(0);
  rendered.rerender({ sourceId: "source-1", whepUrl: null });
  expect(sessions).toHaveLength(0);

  rendered.rerender({
    sourceId: "source-1",
    whepUrl: "https://media/live/whep",
  });
  expect(sessions).toHaveLength(1);
  expect(manager.activeSessionCount).toBe(1);

  rendered.rerender({ sourceId: null, whepUrl: null });
  await act(() => Promise.resolve());
  expect(rendered.result.current.status).toBe("idle");
  expect(manager.activeSessionCount).toBe(0);
  expect(sessions[0]?.closeCount).toBe(1);
});
