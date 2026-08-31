import { use, useEffect, useState, useSyncExternalStore } from "react";

import { StreamSessionManagerContext } from "@/features/video/stream-session/stream-session-manager-context";
import type {
  StreamSessionLease,
  StreamSessionManager,
} from "@/features/video/stream-session/stream-session-manager";
import type {
  StreamSessionListener,
  StreamSessionSnapshot,
} from "@/features/video/stream-session/stream-session";

const IDLE_SNAPSHOT: StreamSessionSnapshot = {
  status: "idle",
  stream: null,
};

/** useSyncExternalStore 的稳定桥接层；effect 只同步外部 Lease，不直接修改 React state。 */
class StreamSessionBinding {
  readonly #manager: StreamSessionManager;
  readonly #listeners = new Set<StreamSessionListener>();
  #lease: StreamSessionLease | null = null;
  #unsubscribeLease: (() => void) | null = null;
  #snapshot = IDLE_SNAPSHOT;

  constructor(manager: StreamSessionManager) {
    this.#manager = manager;
  }

  subscribe = (listener: StreamSessionListener) => {
    this.#listeners.add(listener);
    return () => this.#listeners.delete(listener);
  };

  getSnapshot = () => this.#snapshot;

  configure(sourceId: string | null, whepUrl: string | null) {
    this.disconnect();
    if (sourceId === null || whepUrl === null) {
      return;
    }

    this.#lease = this.#manager.acquire(sourceId, whepUrl);
    this.#snapshot = this.#lease.getSnapshot();
    this.#unsubscribeLease = this.#lease.subscribe(() => {
      if (this.#lease !== null) {
        this.#snapshot = this.#lease.getSnapshot();
        this.#emit();
      }
    });
    this.#emit();
  }

  reconnect = () => this.#lease?.reconnect();

  disconnect() {
    this.#unsubscribeLease?.();
    this.#unsubscribeLease = null;
    this.#lease?.release();
    this.#lease = null;
    this.#snapshot = IDLE_SNAPSHOT;
    this.#emit();
  }

  #emit() {
    this.#listeners.forEach((listener) => listener());
  }
}

/** sourceId 或 whepUrl 为 null 时不占用 Lease，供业务层明确表达当前不需要播放。 */
export function useStreamSession(
  sourceId: string | null,
  whepUrl: string | null,
) {
  const manager = use(StreamSessionManagerContext);
  if (manager === null) {
    throw new Error("useStreamSession 必须在 StreamSessionProvider 内使用。");
  }

  const [binding] = useState(() => new StreamSessionBinding(manager));
  useEffect(() => {
    binding.configure(sourceId, whepUrl);
    return () => binding.disconnect();
  }, [binding, sourceId, whepUrl]);

  const snapshot = useSyncExternalStore(
    binding.subscribe,
    binding.getSnapshot,
    binding.getSnapshot,
  );

  return { ...snapshot, reconnect: binding.reconnect };
}
