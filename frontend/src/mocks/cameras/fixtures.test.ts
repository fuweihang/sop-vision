import { describe, expect, test } from "vitest";

import {
  buildCameraCreateRequest,
  buildCameraDetail,
  buildCameraPage,
  buildCameraSummary,
  buildCameraUpdateRequest,
  buildProblem,
  CAMERA_FIXTURE_IDS,
  CAMERA_FIXTURE_SECRET,
  CAMERA_FIXTURE_TIMES,
} from "@/mocks/cameras/fixtures";

describe("Cameras Fixture Builder", () => {
  test("固定 ID/时间且每次创建相互隔离的合法聚合", () => {
    const first = buildCameraDetail();
    const second = buildCameraDetail();

    expect(first).toEqual(second);
    expect(first).not.toBe(second);
    expect(first.sources).not.toBe(second.sources);
    expect(first.camera_id).toBe(CAMERA_FIXTURE_IDS.primaryCamera);
    expect(first.created_at).toBe(CAMERA_FIXTURE_TIMES.createdAt);
    expect(
      first.sources.filter((source) => source.is_default_preview),
    ).toHaveLength(1);
    expect(first.default_preview_source_id).toBe(first.sources[0]?.source_id);
    expect(first.source_count).toBe(first.sources.length);
    expect(first.online_source_count).toBe(1);
    expect(first.status).toBe("DEGRADED");
  });

  test("根据 Source 状态派生在线计数和聚合状态", () => {
    const detail = buildCameraDetail({
      sources: [
        { status: "OFFLINE", error: "MTX_CONTROL_API_UNAVAILABLE" },
        { status: "OFFLINE", error: "MTX_CONTROL_API_UNAVAILABLE" },
      ],
      defaultSourceIndex: 1,
    });

    expect(detail.status).toBe("OFFLINE");
    expect(detail.online_source_count).toBe(0);
    expect(detail.default_preview_source_id).toBe(
      CAMERA_FIXTURE_IDS.secondarySource,
    );
    expect(detail.sources[1]?.is_default_preview).toBe(true);
  });

  test("RTSP URL 按组件编码凭据、Path 和 query", () => {
    const detail = buildCameraDetail({
      username: "operator@:%# name",
      password: "secret@:%# word",
      sources: [
        {
          url_suffix:
            "Streaming Folder/track#1?token=a:b%# c&mode=main stream&enabled",
        },
      ],
    });

    expect(detail.sources[0]?.rtsp_url).toBe(
      "rtsp://operator%40%3A%25%23%20name:secret%40%3A%25%23%20word@192.0.2.64:554/" +
        "Streaming%20Folder/track%231?token=a%3Ab%25%23%20c&mode=main%20stream&enabled",
    );
  });

  test("写请求保留敏感配置，非详情响应严格排除敏感字段", () => {
    const detail = buildCameraDetail();
    const createRequest = buildCameraCreateRequest(detail);
    const updateRequest = buildCameraUpdateRequest(detail);
    const nonDetailPayloads = [
      buildCameraSummary(detail),
      buildCameraPage({ items: [buildCameraSummary(detail)] }),
      buildProblem({
        status: 503,
        code: "DATABASE_UNAVAILABLE",
        instance: "/api/v1/cameras",
      }),
    ];

    expect(createRequest.password).toBe(CAMERA_FIXTURE_SECRET);
    expect(updateRequest.password).toBe(CAMERA_FIXTURE_SECRET);
    for (const payload of nonDetailPayloads) {
      const serialized = JSON.stringify(payload);
      expect(serialized).not.toContain(CAMERA_FIXTURE_SECRET);
      expect(serialized).not.toContain("fixture-camera-user");
      expect(serialized).not.toContain("url_suffix");
      expect(serialized).not.toContain("rtsp://");
    }
  });

  test("拒绝无 Source 或默认下标越界的伪合法 Fixture", () => {
    expect(() => buildCameraDetail({ sources: [] })).toThrow(
      "Camera Fixture 至少需要一路 Source。",
    );
    expect(() => buildCameraDetail({ defaultSourceIndex: 99 })).toThrow(
      "Camera Fixture 的 defaultSourceIndex 必须指向现有 Source。",
    );
  });
});
