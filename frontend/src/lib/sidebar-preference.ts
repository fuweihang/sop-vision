export const SIDEBAR_STATE_COOKIE_NAME = "sidebar_state";

/**
 * Sidebar 缺少有效持久化值时保持展开，避免损坏的 cookie 隐藏主导航。
 */
export function parseSidebarDefaultOpen(cookieHeader: string): boolean {
  const cookie = cookieHeader.split(";").find((entry) => {
    const separatorIndex = entry.indexOf("=");

    return entry.slice(0, separatorIndex).trim() === SIDEBAR_STATE_COOKIE_NAME;
  });

  if (cookie === undefined) {
    return true;
  }

  const separatorIndex = cookie.indexOf("=");
  const value = cookie.slice(separatorIndex + 1).trim();

  if (value === "true") {
    return true;
  }

  if (value === "false") {
    return false;
  }

  return true;
}

export function getSidebarDefaultOpen(): boolean {
  return typeof document === "undefined"
    ? true
    : parseSidebarDefaultOpen(document.cookie);
}
