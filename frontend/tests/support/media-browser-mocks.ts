import { vi } from "vitest";

type MediaPlayImplementation = (this: HTMLMediaElement) => Promise<void>;
type MediaPauseImplementation = (this: HTMLMediaElement) => void;

interface InstallMediaElementMocksOptions {
  play?: MediaPlayImplementation;
  pause?: MediaPauseImplementation;
}

const cleanupCallbacks: Array<() => void> = [];

function registerCleanup(callback: () => void) {
  cleanupCallbacks.push(callback);
}

function replaceProperty(
  target: object,
  property: PropertyKey,
  descriptor: PropertyDescriptor,
) {
  const originalDescriptor = Object.getOwnPropertyDescriptor(target, property);
  Object.defineProperty(target, property, {
    configurable: true,
    ...descriptor,
  });
  registerCleanup(() => {
    if (originalDescriptor === undefined) {
      Reflect.deleteProperty(target, property);
    } else {
      Object.defineProperty(target, property, originalDescriptor);
    }
  });
}

/**
 * 安装可按用例定制的 play/pause mock。恢复函数由全局 afterEach 统一调用，因此测试断言中途失败
 * 也不会把媒体原型的 spy 留给下一个用例。
 */
export function installMediaElementMocks({
  play = () => Promise.resolve(),
  pause = () => undefined,
}: InstallMediaElementMocksOptions = {}) {
  const playMock = vi
    .spyOn(HTMLMediaElement.prototype, "play")
    .mockImplementation(play);
  const pauseMock = vi
    .spyOn(HTMLMediaElement.prototype, "pause")
    .mockImplementation(pause);
  registerCleanup(() => pauseMock.mockRestore());
  registerCleanup(() => playMock.mockRestore());
  return { play: playMock, pause: pauseMock };
}

/** 安装会同步派发原生 playing/pause 事件的媒体 mock，用于验证 React 状态与 DOM 状态同步。 */
export function installPlayingMediaElementMocks() {
  return installMediaElementMocks({
    play() {
      this.dispatchEvent(new Event("playing"));
      return Promise.resolve();
    },
    pause() {
      this.dispatchEvent(new Event("pause"));
    },
  });
}

/** 安装完整 Fullscreen 状态机，并精确恢复环境原有的属性描述符。 */
export function installFullscreenMocks() {
  const fullscreenState: { element: Element | null } = { element: null };
  const requestFullscreen = vi.fn(function (this: HTMLElement) {
    fullscreenState.element = this;
    document.dispatchEvent(new Event("fullscreenchange"));
    return Promise.resolve();
  });
  const exitFullscreen = vi.fn(() => {
    fullscreenState.element = null;
    document.dispatchEvent(new Event("fullscreenchange"));
    return Promise.resolve();
  });

  replaceProperty(document, "fullscreenElement", {
    get: () => fullscreenState.element,
  });
  replaceProperty(HTMLElement.prototype, "requestFullscreen", {
    writable: true,
    value: requestFullscreen,
  });
  replaceProperty(document, "exitFullscreen", {
    writable: true,
    value: exitFullscreen,
  });

  return { requestFullscreen, exitFullscreen };
}

/**
 * 安装 requestVideoFrameCallback/cancelVideoFrameCallback，并把回调暴露给测试手动推进首帧。
 */
export function installVideoFrameCallbackMocks() {
  const callbacks: VideoFrameRequestCallback[] = [];
  const requestVideoFrameCallback = vi.fn(
    (callback: VideoFrameRequestCallback) => {
      callbacks.push(callback);
      return callbacks.length;
    },
  );
  const cancelVideoFrameCallback = vi.fn();

  replaceProperty(HTMLVideoElement.prototype, "requestVideoFrameCallback", {
    writable: true,
    value: requestVideoFrameCallback,
  });
  replaceProperty(HTMLVideoElement.prototype, "cancelVideoFrameCallback", {
    writable: true,
    value: cancelVideoFrameCallback,
  });

  return {
    callbacks,
    requestVideoFrameCallback,
    cancelVideoFrameCallback,
  };
}

/** 只恢复本文件安装的媒体边界，不影响用例自己创建的业务 spy。 */
export function restoreMediaBrowserMocks() {
  let callback = cleanupCallbacks.pop();
  while (callback !== undefined) {
    callback();
    callback = cleanupCallbacks.pop();
  }
}
