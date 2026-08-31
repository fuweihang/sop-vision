import type {
  StreamSession,
  StreamSessionListener,
  StreamSessionSnapshot,
  StreamSessionStatus,
} from "@/features/video/stream-session/stream-session";

const RETRY_MESSAGE_SUFFIX = ", retrying in some seconds";

type ReaderFactory = (
  configuration: MediaMTXWebRTCReaderConfiguration,
) => MediaMTXWebRTCReaderInstance;
type ReaderFactoryLoader = () => Promise<ReaderFactory>;

interface WhepSessionOptions {
  readerFactory?: ReaderFactory;
  readerFactoryLoader?: ReaderFactoryLoader;
  mediaStreamFactory?: () => MediaStream;
}

function createOfficialReader(
  configuration: MediaMTXWebRTCReaderConfiguration,
) {
  return new window.MediaMTXWebRTCReader(configuration);
}

/**
 * 官方 reader 约 19 KB 且会在模块顶层写入 window。只有实际创建 WHEP Session 时才加载它，
 * 这样普通页面不会执行 WebRTC 代码，服务端或非浏览器环境导入本模块也不会立即访问 window。
 */
async function loadOfficialReaderFactory(): Promise<ReaderFactory> {
  await import("@/vendor/mediamtx/load-reader");
  return createOfficialReader;
}

/**
 * 把 MediaMTX reader 的回调式接口转换成可订阅快照。
 *
 * Session 不保存、显示或记录 reader 原始错误，因为上游响应可能包含部署地址等信息。reader 自己
 * 负责可恢复连接的重试；这里只根据固定版本的重试后缀区分 failed 与 reconnecting。
 */
export class WhepSession implements StreamSession {
  readonly #whepUrl: string;
  #readerFactory: ReaderFactory | null;
  readonly #readerFactoryLoader: ReaderFactoryLoader;
  #readerFactoryPromise: Promise<ReaderFactory> | null = null;
  readonly #mediaStreamFactory: () => MediaStream;
  readonly #listeners = new Set<StreamSessionListener>();
  #reader: MediaMTXWebRTCReaderInstance | null = null;
  #generation = 0;
  #snapshot: StreamSessionSnapshot = {
    status: "idle",
    stream: null,
  };

  constructor(whepUrl: string, options: WhepSessionOptions = {}) {
    this.#whepUrl = whepUrl;
    this.#readerFactory = options.readerFactory ?? null;
    this.#readerFactoryLoader =
      options.readerFactoryLoader ?? loadOfficialReaderFactory;
    this.#mediaStreamFactory =
      options.mediaStreamFactory ?? (() => new MediaStream());
  }

  getSnapshot = () => this.#snapshot;

  subscribe = (listener: StreamSessionListener) => {
    this.#listeners.add(listener);
    return () => this.#listeners.delete(listener);
  };

  connect() {
    if (this.#snapshot.status !== "idle") {
      return;
    }
    this.#startReader();
  }

  reconnect = () => {
    if (this.#snapshot.status === "closed") {
      return;
    }

    this.#generation += 1;
    this.#reader?.close();
    this.#reader = null;
    this.#stopCurrentStream();
    this.#startReader();
  };

  close = () => {
    if (this.#snapshot.status === "closed") {
      return;
    }

    // generation 使旧 reader 已排队的回调失效，避免关闭后重新发布 playing 状态。
    this.#generation += 1;
    this.#reader?.close();
    this.#reader = null;
    this.#stopCurrentStream();
    this.#publish("closed", null);
    this.#listeners.clear();
  };

  #startReader() {
    const generation = ++this.#generation;
    this.#publish("connecting", null);

    if (this.#readerFactory !== null) {
      this.#createReader(generation, this.#readerFactory);
      return;
    }

    // 动态 import 完成前 Session 已对消费者发布 connecting；关闭或重连后，generation 会阻止旧任务
    // 创建 reader。加载失败只发布固定状态，不把 import 或部署错误交给 UI。
    void this.#loadReaderFactory()
      .then((readerFactory) => this.#createReader(generation, readerFactory))
      .catch(() => {
        if (
          generation === this.#generation &&
          this.#snapshot.status !== "closed"
        ) {
          this.#publish("failed", null);
        }
      });
  }

  #loadReaderFactory() {
    if (this.#readerFactory !== null) {
      return Promise.resolve(this.#readerFactory);
    }
    if (this.#readerFactoryPromise === null) {
      const loadPromise = this.#readerFactoryLoader().then((readerFactory) => {
        this.#readerFactory = readerFactory;
        return readerFactory;
      });
      // 加载失败后允许用户通过“刷新当前流”再次尝试，而不是永久缓存 rejected Promise。
      this.#readerFactoryPromise = loadPromise.catch((error: unknown) => {
        this.#readerFactoryPromise = null;
        throw error;
      });
    }
    return this.#readerFactoryPromise;
  }

  #createReader(generation: number, readerFactory: ReaderFactory) {
    if (generation !== this.#generation || this.#snapshot.status === "closed") {
      return;
    }

    try {
      this.#reader = readerFactory({
        url: this.#whepUrl,
        onError: (error) => this.#handleError(generation, error),
        onTrack: (event) => this.#handleTrack(generation, event),
      });
    } catch {
      this.#publish("failed", null);
    }
  }

  #handleError(generation: number, error: string) {
    if (generation !== this.#generation || this.#snapshot.status === "closed") {
      return;
    }

    this.#stopCurrentStream();
    const isRetrying = error.endsWith(RETRY_MESSAGE_SUFFIX);
    this.#publish(isRetrying ? "reconnecting" : "failed", null);
  }

  #handleTrack(generation: number, event: RTCTrackEvent) {
    if (generation !== this.#generation || this.#snapshot.status === "closed") {
      return;
    }

    const stream = this.#snapshot.stream ?? this.#mediaStreamFactory();
    if (!stream.getTracks().some((track) => track.id === event.track.id)) {
      stream.addTrack(event.track);
    }
    // 音频 Track 可能先于视频 Track 到达。播放器只有拿到视频 Track 后才具备出画条件，
    // 过早发布 playing 会让连接 loading 在黑屏阶段消失。
    this.#publish(
      stream.getVideoTracks().length > 0 ? "playing" : "connecting",
      stream,
    );
  }

  #stopCurrentStream() {
    this.#snapshot.stream?.getTracks().forEach((track) => track.stop());
  }

  #publish(status: StreamSessionStatus, stream: MediaStream | null) {
    this.#snapshot = { status, stream };
    this.#listeners.forEach((listener) => listener());
  }
}

/** 默认工厂只在 Manager 首次 acquire 时开始连接，并在此时动态加载官方 reader。 */
export function createWhepSession(whepUrl: string): WhepSession {
  const session = new WhepSession(whepUrl);
  session.connect();
  return session;
}
