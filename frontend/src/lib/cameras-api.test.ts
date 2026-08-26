import axios, {
  AxiosHeaders,
  type AxiosAdapter,
  type InternalAxiosRequestConfig,
} from "axios";
import { describe, expect, test } from "vitest";

import {
  createCamera,
  deleteCamera,
  getCamera,
  listCameras,
  prepareCameraSourcePlayback,
  setDefaultPreviewSource,
  updateCamera,
  type CameraCreateRequest,
  type CameraUpdateRequest,
} from "@/lib/cameras-api";

const CAMERA_ID = "6f9619ff-8b86-4e4f-9f68-bb3f8f6f4f21";
const SOURCE_ID = "3f2504e0-4f89-41d3-9a0c-0305e82c3301";

const createRequest: CameraCreateRequest = {
  name: "洗手区 01",
  ip_address: "192.0.2.64",
  rtsp_port: 554,
  username: "test-user",
  password: "test-password",
  sources: [
    {
      name: "主码流",
      url_suffix: "Streaming/Channels/101",
      is_default_preview: true,
    },
  ],
};

const updateRequest: CameraUpdateRequest = {
  ...createRequest,
  name: "洗手区东侧 01",
  sources: [
    {
      source_id: SOURCE_ID,
      name: "主码流",
      url_suffix: "Streaming/Channels/101",
      is_default_preview: true,
    },
  ],
};

interface RecordedRequest {
  readonly method: string | undefined;
  readonly url: string | undefined;
  readonly params: unknown;
  readonly data: unknown;
}

function createRecordingClient() {
  const requests: RecordedRequest[] = [];
  const adapter: AxiosAdapter = (config: InternalAxiosRequestConfig) => {
    requests.push({
      method: config.method,
      url: config.url,
      params: config.params,
      data:
        typeof config.data === "string"
          ? (JSON.parse(config.data) as unknown)
          : config.data,
    });

    return Promise.resolve({
      data: { operation_result: config.url },
      status:
        config.method === "post" ? 201 : config.method === "delete" ? 204 : 200,
      statusText: "OK",
      headers: new AxiosHeaders(),
      config,
    });
  };

  return {
    client: axios.create({ adapter }),
    requests,
  };
}

describe("Cameras operation Client", () => {
  test("七个请求严格使用 OpenAPI 冻结的方法、路径、参数和请求体", async () => {
    const { client, requests } = createRecordingClient();

    await listCameras({ q: "  洗手区  ", page: 2, page_size: 10 }, client);
    await createCamera(createRequest, client);
    await getCamera(CAMERA_ID, client);
    await updateCamera(CAMERA_ID, updateRequest, client);
    await setDefaultPreviewSource(CAMERA_ID, { source_id: SOURCE_ID }, client);
    await deleteCamera(CAMERA_ID, client);
    await prepareCameraSourcePlayback(SOURCE_ID, client);

    expect(requests).toEqual([
      {
        method: "get",
        url: "/cameras",
        params: { q: "洗手区", page: 2, page_size: 10 },
        data: undefined,
      },
      {
        method: "post",
        url: "/cameras",
        params: undefined,
        data: createRequest,
      },
      {
        method: "get",
        url: `/cameras/${CAMERA_ID}`,
        params: undefined,
        data: undefined,
      },
      {
        method: "put",
        url: `/cameras/${CAMERA_ID}`,
        params: undefined,
        data: updateRequest,
      },
      {
        method: "patch",
        url: `/cameras/${CAMERA_ID}/default-preview-source`,
        params: undefined,
        data: { source_id: SOURCE_ID },
      },
      {
        method: "delete",
        url: `/cameras/${CAMERA_ID}`,
        params: undefined,
        data: undefined,
      },
      {
        method: "post",
        url: `/camera-sources/${SOURCE_ID}/playback`,
        params: undefined,
        data: undefined,
      },
    ]);
  });

  test("路径参数编码由 Client 统一处理", async () => {
    const { client, requests } = createRecordingClient();
    await getCamera("id/with/slash", client);
    expect(requests[0]?.url).toBe("/cameras/id%2Fwith%2Fslash");
  });
});
