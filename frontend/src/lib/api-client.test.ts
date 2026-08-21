import { describe, expect, it } from "vitest";

import { apiClient, resolveApiBaseUrl } from "@/lib/api-client";

describe("resolveApiBaseUrl", () => {
  it.each([undefined, "", "   "])(
    "配置缺失或为空时使用本地默认地址",
    (value) => {
      expect(resolveApiBaseUrl(value)).toBe("http://localhost:3001/api/v1");
    },
  );

  it("清理环境变量首尾空白", () => {
    expect(resolveApiBaseUrl("  https://api.example.com/api/v1  ")).toBe(
      "https://api.example.com/api/v1",
    );
  });

  it("接受大小写不敏感的 HTTP 协议", () => {
    expect(resolveApiBaseUrl("HTTPS://api.example.com/api/v1")).toBe(
      "HTTPS://api.example.com/api/v1",
    );
  });

  it("保留由 Axios 处理的尾斜杠", () => {
    expect(resolveApiBaseUrl("https://api.example.com/api/v1///")).toBe(
      "https://api.example.com/api/v1///",
    );
  });

  it.each([
    "/api/v1",
    "api.example.com/api/v1",
    "https:api.example.com/api/v1",
    "ftp://api.example.com/api/v1",
  ])("拒绝无效或非 HTTP(S) 的地址：%s", (value) => {
    expect(() => resolveApiBaseUrl(value)).toThrow(
      "VITE_API_BASE_URL 必须是有效的绝对 HTTP(S) URL",
    );
  });
});

describe("apiClient", () => {
  it("由 Axios 将 baseURL 与相对请求地址规范为单个斜杠", () => {
    const baseURL = resolveApiBaseUrl("http://localhost:3001/api/v1///");

    expect(apiClient.getUri({ baseURL, url: "/health/live" })).toBe(
      "http://localhost:3001/api/v1/health/live",
    );
  });
});
