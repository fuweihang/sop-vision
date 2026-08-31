import { createContext } from "react";

import type { StreamSessionManager } from "@/features/video/stream-session/stream-session-manager";

export const StreamSessionManagerContext =
  createContext<StreamSessionManager | null>(null);
