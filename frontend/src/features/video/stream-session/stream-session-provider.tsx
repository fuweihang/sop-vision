import { type PropsWithChildren, useEffect, useRef, useState } from "react";

import { createWhepSession } from "@/features/video/mediamtx/whep-session";
import { StreamSessionManagerContext } from "@/features/video/stream-session/stream-session-manager-context";
import { StreamSessionManager } from "@/features/video/stream-session/stream-session-manager";

interface StreamSessionProviderProps extends PropsWithChildren {
  manager?: StreamSessionManager;
}

/**
 * App 级 Provider 保证 Card、Detail 和后续 Detection 使用同一个 Manager。Provider 拥有最终选定的
 * Manager，包括通过 prop 注入的测试 Manager；真实卸载后统一关闭，调用方不得继续复用。
 */
export function StreamSessionProvider({
  children,
  manager: providedManager,
}: StreamSessionProviderProps) {
  const [manager] = useState(
    () => providedManager ?? new StreamSessionManager(createWhepSession),
  );
  const closeTimerRef = useRef<number | null>(null);

  useEffect(() => {
    // React Strict Mode 会立刻执行一次 cleanup 再重新挂载；重新挂载时取消关闭，保留同一个 Manager。
    if (closeTimerRef.current !== null) {
      window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }

    return () => {
      closeTimerRef.current = window.setTimeout(() => manager.close(), 0);
    };
  }, [manager]);

  return (
    <StreamSessionManagerContext value={manager}>
      {children}
    </StreamSessionManagerContext>
  );
}
