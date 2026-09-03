import { AxiosError, type AxiosAdapter } from "axios";
import { afterEach, describe, expect, test, vi } from "vitest";

import { apiClient } from "@/lib/api-client";
import { ApiTransportError } from "@/lib/api-errors";

const SENSITIVE_VALUE = "shared-contract-secret-must-not-leak";

const originalAdapter = apiClient.defaults.adapter;

afterEach(() => {
  if (originalAdapter === undefined) {
    delete apiClient.defaults.adapter;
  } else {
    apiClient.defaults.adapter = originalAdapter;
  }
});

describe("单一 Axios Client 安全边界", () => {
  test("写请求断网时抛出脱敏错误且不写 console 或浏览器持久化存储", async () => {
    const consoleError = vi.spyOn(console, "error");
    const consoleLog = vi.spyOn(console, "log");
    let originalAxiosError: unknown;

    const failingAdapter: AxiosAdapter = (config) => {
      // 模拟真实 Axios 网络错误：config.data 已包含序列化后的密码。拦截器必须在错误离开
      // Client 前移除整个 config，而不是依赖每个调用方记得脱敏。
      const axiosError = new AxiosError(
        "Network Error",
        AxiosError.ERR_NETWORK,
        config,
        {},
      );
      originalAxiosError = axiosError;
      return Promise.reject(axiosError);
    };
    apiClient.defaults.adapter = failingAdapter;

    const request = {
      name: "公共 Client 安全测试",
      password: SENSITIVE_VALUE,
    };

    let caught: unknown;
    try {
      await apiClient.post("/security-boundary-test", request);
    } catch (error) {
      caught = error;
    }

    expect(JSON.stringify(originalAxiosError)).toContain(SENSITIVE_VALUE);
    expect(caught).toBeInstanceOf(ApiTransportError);
    expect(JSON.stringify(caught)).not.toContain(SENSITIVE_VALUE);
    expect(consoleError).not.toHaveBeenCalled();
    expect(consoleLog).not.toHaveBeenCalled();
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
});
