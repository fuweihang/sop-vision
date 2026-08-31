import type {
  StreamSession,
  StreamSessionFactory,
  StreamSessionListener,
  StreamSessionSnapshot,
} from "@/features/video/stream-session/stream-session";

interface SessionEntry {
  sourceId: string;
  streamUrl: string;
  session: StreamSession;
  refCount: number;
  disposeVersion: number;
  listeners: Set<StreamSessionListener>;
  unsubscribeSession: () => void;
}

export interface StreamSessionLease {
  readonly sourceId: string;
  getSnapshot(): StreamSessionSnapshot;
  subscribe(listener: StreamSessionListener): () => void;
  reconnect(): void;
  release(): void;
}

/**
 * 同一 source_id 只保留一路 Stream Session，具体传输实现由构造函数注入。引用归零后的关闭延迟到
 * microtask，专门吸收 React Strict Mode 紧邻的 effect cleanup/acquire；真正没有消费者时仍会在
 * 当前任务结束前释放媒体资源。
 */
export class StreamSessionManager {
  readonly #sessionFactory: StreamSessionFactory;
  readonly #entries = new Map<string, SessionEntry>();
  #closed = false;

  /**
   * Manager 只依赖通用 Session 工厂。生产环境在 Provider 组合 MediaMTX 实现，测试可以注入 Fake，
   * 因而本模块不会在导入时加载浏览器专用的 WHEP reader。
   */
  constructor(sessionFactory: StreamSessionFactory) {
    this.#sessionFactory = sessionFactory;
  }

  acquire(sourceId: string, streamUrl: string): StreamSessionLease {
    if (this.#closed) {
      throw new Error("StreamSessionManager 已关闭，不能继续创建播放会话。");
    }

    let entry = this.#entries.get(sourceId);
    if (entry === undefined) {
      entry = this.#createEntry(sourceId, streamUrl);
      this.#entries.set(sourceId, entry);
    } else if (entry.streamUrl !== streamUrl) {
      this.#replaceSession(entry, streamUrl);
    }

    entry.refCount += 1;
    entry.disposeVersion += 1;
    let released = false;

    return {
      sourceId,
      getSnapshot: () => entry.session.getSnapshot(),
      subscribe: (listener) => {
        entry.listeners.add(listener);
        return () => entry.listeners.delete(listener);
      },
      reconnect: () => entry.session.reconnect(),
      release: () => {
        if (released) {
          return;
        }
        released = true;
        this.#releaseEntry(entry);
      },
    };
  }

  close() {
    if (this.#closed) {
      return;
    }
    this.#closed = true;

    this.#entries.forEach((entry) => this.#disposeEntry(entry));
    this.#entries.clear();
  }

  /** 只供测试和诊断确认引用是否完成清理，不暴露 Session 或播放地址。 */
  get activeSessionCount() {
    return this.#entries.size;
  }

  #createEntry(sourceId: string, streamUrl: string): SessionEntry {
    const session = this.#sessionFactory(streamUrl);
    const entry: SessionEntry = {
      sourceId,
      streamUrl,
      session,
      refCount: 0,
      disposeVersion: 0,
      listeners: new Set(),
      unsubscribeSession: () => undefined,
    };
    entry.unsubscribeSession = session.subscribe(() => {
      entry.listeners.forEach((listener) => listener());
    });
    return entry;
  }

  #replaceSession(entry: SessionEntry, streamUrl: string) {
    entry.unsubscribeSession();
    entry.session.close();
    entry.streamUrl = streamUrl;
    entry.session = this.#sessionFactory(streamUrl);
    entry.unsubscribeSession = entry.session.subscribe(() => {
      entry.listeners.forEach((listener) => listener());
    });
    entry.listeners.forEach((listener) => listener());
  }

  #releaseEntry(entry: SessionEntry) {
    if (entry.refCount === 0) {
      return;
    }
    entry.refCount -= 1;
    const disposeVersion = ++entry.disposeVersion;

    if (entry.refCount !== 0) {
      return;
    }

    queueMicrotask(() => {
      if (
        entry.refCount === 0 &&
        entry.disposeVersion === disposeVersion &&
        this.#entries.get(entry.sourceId) === entry
      ) {
        this.#entries.delete(entry.sourceId);
        this.#disposeEntry(entry);
      }
    });
  }

  #disposeEntry(entry: SessionEntry) {
    entry.unsubscribeSession();
    entry.listeners.clear();
    entry.session.close();
  }
}
