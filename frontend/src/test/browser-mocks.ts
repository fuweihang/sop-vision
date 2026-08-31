const DEFAULT_VIEWPORT_WIDTH = 1024;

function evaluateMediaQuery(query: string) {
  const maxWidth = /\(max-width:\s*(\d+)px\)/.exec(query)?.[1];
  const minWidth = /\(min-width:\s*(\d+)px\)/.exec(query)?.[1];
  const hasWidthConstraint = maxWidth !== undefined || minWidth !== undefined;

  if (maxWidth !== undefined && window.innerWidth > Number(maxWidth)) {
    return false;
  }

  if (minWidth !== undefined && window.innerWidth < Number(minWidth)) {
    return false;
  }

  return (
    hasWidthConstraint ||
    query.includes("hover: hover") ||
    query.includes("pointer: fine")
  );
}

class TestMediaQueryList extends EventTarget implements MediaQueryList {
  readonly media: string;
  onchange:
    ((this: MediaQueryList, ev: MediaQueryListEvent) => unknown) | null = null;
  #matches: boolean;
  readonly #legacyListeners = new Set<(event: MediaQueryListEvent) => void>();

  constructor(query: string) {
    super();
    this.media = query;
    this.#matches = evaluateMediaQuery(query);
  }

  get matches() {
    return this.#matches;
  }

  addListener(callback: ((event: MediaQueryListEvent) => void) | null) {
    if (callback !== null) {
      this.#legacyListeners.add(callback);
    }
  }

  removeListener(callback: ((event: MediaQueryListEvent) => void) | null) {
    if (callback !== null) {
      this.#legacyListeners.delete(callback);
    }
  }

  refresh() {
    const matches = evaluateMediaQuery(this.media);

    if (matches === this.#matches) {
      return;
    }

    this.#matches = matches;
    const event = Object.assign(new Event("change"), {
      matches,
      media: this.media,
    });
    this.dispatchEvent(event);
    this.onchange?.call(this, event);
    this.#legacyListeners.forEach((listener) => listener(event));
  }
}

const mediaQueryLists = new Set<TestMediaQueryList>();

export function installMatchMediaMock() {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: (query: string) => {
      const mediaQueryList = new TestMediaQueryList(query);
      mediaQueryLists.add(mediaQueryList);
      return mediaQueryList;
    },
  });
}

export function setViewportWidth(width: number) {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: width,
  });

  mediaQueryLists.forEach((mediaQueryList) => mediaQueryList.refresh());
}

/** 驱动依赖 Page Visibility API 的后台刷新测试，不通过私有 Query 状态模拟焦点。 */
export function setDocumentVisibility(
  visibilityState: DocumentVisibilityState,
) {
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    value: visibilityState,
  });
  document.dispatchEvent(new Event("visibilitychange"));
}

function clearDocumentCookies() {
  document.cookie.split(";").forEach((cookie) => {
    const separatorIndex = cookie.indexOf("=");
    const name = cookie.slice(0, separatorIndex).trim();

    if (name !== "") {
      document.cookie = `${name}=; path=/; max-age=0`;
    }
  });
}

export function resetBrowserState() {
  mediaQueryLists.clear();
  setViewportWidth(DEFAULT_VIEWPORT_WIDTH);
  setDocumentVisibility("visible");
  installMatchMediaMock();
  clearDocumentCookies();
  localStorage.clear();
  sessionStorage.clear();
  document.documentElement.className = "";
  document.documentElement.removeAttribute("style");
  document.body.className = "";
  document.body.removeAttribute("style");
  // jsdom 自带的 scrollTo 只会输出“未实现”警告。Router 的滚动恢复不依赖测试中的真实滚动位置，
  // 用确定的空实现替换它，避免重复警告淹没真正的 console error。
  Object.defineProperty(window, "scrollTo", {
    configurable: true,
    writable: true,
    value: () => undefined,
  });
}
