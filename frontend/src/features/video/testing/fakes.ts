import type {
  StreamSession,
  StreamSessionListener,
  StreamSessionSnapshot,
} from "@/features/video/stream-session/stream-session";

const DEFAULT_SNAPSHOT: StreamSessionSnapshot = {
  status: "connecting",
  stream: null,
};

/** 单元和页面测试手动推进状态，避免 jsdom 创建真实 RTCPeerConnection 或访问 MediaMTX。 */
export class FakeStreamSession implements StreamSession {
  readonly #listeners = new Set<StreamSessionListener>();
  #snapshot: StreamSessionSnapshot;
  reconnectCount = 0;
  closeCount = 0;

  constructor(snapshot: StreamSessionSnapshot = DEFAULT_SNAPSHOT) {
    this.#snapshot = snapshot;
  }

  getSnapshot = () => this.#snapshot;

  subscribe = (listener: StreamSessionListener) => {
    this.#listeners.add(listener);
    return () => this.#listeners.delete(listener);
  };

  reconnect = () => {
    this.reconnectCount += 1;
    this.emit({ status: "connecting", stream: null });
  };

  close = () => {
    this.closeCount += 1;
    this.emit({ status: "closed", stream: null });
    this.#listeners.clear();
  };

  emit(snapshot: StreamSessionSnapshot) {
    this.#snapshot = snapshot;
    this.#listeners.forEach((listener) => listener());
  }
}
