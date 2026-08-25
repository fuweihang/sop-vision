import { QueryClient } from "@tanstack/react-query";

// CameraDetail 包含用户名、密码和完整 RTSP URL。Foundation 阶段故意只创建内存 Query cache，
// 不接入 localStorage/IndexedDB persister；未来若增加离线缓存，必须先显式排除敏感详情 Key。
export const queryClient = new QueryClient();
