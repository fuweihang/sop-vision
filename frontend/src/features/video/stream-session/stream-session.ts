export type StreamSessionStatus =
  "idle" | "connecting" | "playing" | "reconnecting" | "failed" | "closed";

/** React 和业务组件只读取通用快照，不接触 MediaMTX reader 等具体传输实现。 */
export interface StreamSessionSnapshot {
  status: StreamSessionStatus;
  stream: MediaStream | null;
}

export type StreamSessionListener = () => void;

/** Session Manager 依赖的最小接口，也是具体传输适配器和测试 Fake 的实现边界。 */
export interface StreamSession {
  getSnapshot(): StreamSessionSnapshot;
  subscribe(listener: StreamSessionListener): () => void;
  reconnect(): void;
  close(): void;
}

export type StreamSessionFactory = (streamUrl: string) => StreamSession;
