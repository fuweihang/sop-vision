import { useCallback, useEffect, useState } from "react";

/**
 * 网页全屏只改变当前 VideoSurface 的布局，不调用 Fullscreen API。滚动锁定只在模式有效期间存在，
 * 并恢复进入前的 body inline style，避免路由离开或组件卸载后页面仍无法滚动。
 */
export function useVideoPageFullscreen() {
  const [isPageFullscreen, setIsPageFullscreen] = useState(false);

  const requestPageFullscreen = useCallback(() => {
    setIsPageFullscreen(true);
  }, []);
  const exitPageFullscreen = useCallback(() => {
    setIsPageFullscreen(false);
  }, []);
  useEffect(() => {
    if (!isPageFullscreen) {
      return;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [isPageFullscreen]);

  return {
    state: { isPageFullscreen },
    actions: {
      requestPageFullscreen,
      exitPageFullscreen,
    },
  };
}
