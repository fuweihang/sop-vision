import { expect, test } from "vitest";

import { StreamSessionManager } from "@/features/video/stream-session/stream-session-manager";
import { FakeStreamSession } from "@/features/video/testing/fakes";

test("同一 Source 共享 Session，最后一个 Lease release 后才关闭", async () => {
  const sessions: FakeStreamSession[] = [];
  const manager = new StreamSessionManager(() => {
    const session = new FakeStreamSession();
    sessions.push(session);
    return session;
  });

  const first = manager.acquire("source-1", "https://media/live/whep");
  const second = manager.acquire("source-1", "https://media/live/whep");
  expect(sessions).toHaveLength(1);
  expect(manager.activeSessionCount).toBe(1);

  first.release();
  await Promise.resolve();
  expect(sessions[0]?.closeCount).toBe(0);
  expect(manager.activeSessionCount).toBe(1);

  second.release();
  second.release();
  await Promise.resolve();
  expect(sessions[0]?.closeCount).toBe(1);
  expect(manager.activeSessionCount).toBe(0);
});

test("Strict Mode 紧邻 reacquire 复用待释放项，不重复创建连接", async () => {
  const sessions: FakeStreamSession[] = [];
  const manager = new StreamSessionManager(() => {
    const session = new FakeStreamSession();
    sessions.push(session);
    return session;
  });

  const first = manager.acquire("source-1", "https://media/live/whep");
  first.release();
  const remounted = manager.acquire("source-1", "https://media/live/whep");
  await Promise.resolve();

  expect(sessions).toHaveLength(1);
  expect(sessions[0]?.closeCount).toBe(0);
  remounted.release();
  await Promise.resolve();
  expect(sessions[0]?.closeCount).toBe(1);
});

test("同一 Source 收到新 URL 时替换 Session，并通知既有 Lease", () => {
  const sessions: FakeStreamSession[] = [];
  const manager = new StreamSessionManager(() => {
    const session = new FakeStreamSession();
    sessions.push(session);
    return session;
  });
  const existing = manager.acquire("source-1", "https://media/old/whep");
  let notificationCount = 0;
  existing.subscribe(() => {
    notificationCount += 1;
  });

  const latest = manager.acquire("source-1", "https://media/new/whep");
  expect(sessions).toHaveLength(2);
  expect(sessions[0]?.closeCount).toBe(1);
  expect(notificationCount).toBeGreaterThan(0);
  expect(existing.getSnapshot()).toBe(sessions[1]?.getSnapshot());

  existing.release();
  latest.release();
  manager.close();
  expect(sessions[1]?.closeCount).toBe(1);
});
