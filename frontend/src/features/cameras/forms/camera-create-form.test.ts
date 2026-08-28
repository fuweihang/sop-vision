import { describe, expect, test } from "vitest";

import {
  CAMERA_CREATE_DEFAULT_VALUES,
  cameraCreateFormSchema,
  createEmptyCameraSource,
  toCameraCreateRequest,
} from "@/features/cameras/forms/camera-create-form";

function validFormValues() {
  return {
    name: "  洗手区 01  ",
    ip_address: "192.0.2.64",
    rtsp_port: 554,
    username: " camera-user ",
    password: " camera-password ",
    sources: [
      {
        name: "  主码流  ",
        url_suffix: "  /Streaming/Channels/101  ",
        is_default_preview: true,
      },
      {
        name: "子码流",
        url_suffix: "Streaming/Channels/102",
        is_default_preview: false,
      },
    ],
  };
}

describe("Camera 创建表单 Schema", () => {
  test("默认值包含端口 554 和唯一默认 Source", () => {
    expect(CAMERA_CREATE_DEFAULT_VALUES).toEqual({
      name: "",
      ip_address: "",
      rtsp_port: 554,
      username: "",
      password: "",
      sources: [{ name: "", url_suffix: "", is_default_preview: true }],
    });
    expect(createEmptyCameraSource()).toEqual({
      name: "",
      url_suffix: "",
      is_default_preview: false,
    });
  });

  test("规范化名称和 URL 后缀，但不修改设备凭据", () => {
    const result = cameraCreateFormSchema.parse(validFormValues());
    const request = toCameraCreateRequest(result);

    expect(request).toEqual({
      name: "洗手区 01",
      ip_address: "192.0.2.64",
      rtsp_port: 554,
      username: " camera-user ",
      password: " camera-password ",
      sources: [
        {
          name: "主码流",
          url_suffix: "Streaming/Channels/101",
          is_default_preview: true,
        },
        {
          name: "子码流",
          url_suffix: "Streaming/Channels/102",
          is_default_preview: false,
        },
      ],
    });
    expect(request.sources[0]).not.toHaveProperty("source_id");
  });

  test("按规范化后的大小写敏感后缀发现重复", () => {
    const values = validFormValues();
    values.sources[1]!.url_suffix = "/Streaming/Channels/101";

    const result = cameraCreateFormSchema.safeParse(values);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            path: ["sources", 1, "url_suffix"],
            message: "URL 后缀不能与第 1 路视频源重复。",
          }),
        ]),
      );
    }
  });

  test.each([
    [[false, false], ["sources"]],
    [
      [true, true],
      ["sources", 1, "is_default_preview"],
    ],
  ])("拒绝默认源选择 %j", (defaults, expectedPath) => {
    const values = validFormValues();
    values.sources.forEach((source, index) => {
      source.is_default_preview = defaults[index] ?? false;
    });

    const result = cameraCreateFormSchema.safeParse(values);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ path: expectedPath }),
        ]),
      );
    }
  });
});
