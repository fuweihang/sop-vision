import { AxiosError, type AxiosAdapter } from "axios";
import { afterEach, describe, expect, test, vi } from "vitest";

import { apiClient } from "@/lib/api-client";
import { ApiTransportError } from "@/lib/api-errors";
import {
  createCamera,
  type CameraCreateRequest,
} from "@/features/cameras/api/cameras-api";
import { CAMERA_FIXTURE_SECRET } from "@/mocks/cameras/fixtures";

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

    const request: CameraCreateRequest = {
      name: "安全测试 Camera",
      ip_address: "192.0.2.10",
      rtsp_port: 554,
      username: "test-user",
      password: CAMERA_FIXTURE_SECRET,
      sources: [
        {
          name: "主码流",
          url_suffix: "Streaming/Channels/101",
          is_default_preview: true,
        },
      ],
    };

    let caught: unknown;
    try {
      await createCamera(request);
    } catch (error) {
      caught = error;
    }

    expect(JSON.stringify(originalAxiosError)).toContain(CAMERA_FIXTURE_SECRET);
    expect(caught).toBeInstanceOf(ApiTransportError);
    expect(JSON.stringify(caught)).not.toContain(CAMERA_FIXTURE_SECRET);
    expect(consoleError).not.toHaveBeenCalled();
    expect(consoleLog).not.toHaveBeenCalled();
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
});
