import axios from "axios";

import { mapApiError } from "@/lib/api-errors";

const DEFAULT_API_BASE_URL = "http://localhost:3001/api/v1";

export const apiBaseUrl =
  import.meta.env.VITE_API_BASE_URL?.trim() || DEFAULT_API_BASE_URL;

export const apiClient = axios.create({
  baseURL: apiBaseUrl,
});

// AxiosError 会保留 config.data 与 response.data；写请求失败时其中可能包含 Camera 密码。
// 在唯一生产 Client 的响应边界立即转换错误，能保证路由错误边界、console 或未来的错误上报
// 即使直接记录抛出的对象，也不会意外序列化原始请求体或非 Problem 响应体。
apiClient.interceptors.response.use(undefined, (error: unknown) => {
  throw mapApiError(error);
});
