import type {
  CameraCreateRequest,
  CameraDetail,
  CameraPage,
  CameraUpdateRequest,
  DefaultPreviewSourceResponse,
  PlaybackInfo,
} from "@/features/cameras/api/cameras-api";
import type { ProblemDetails } from "@/lib/api-errors";

export type CameraSummary = CameraPage["items"][number];
export type CameraSourceDetail = CameraDetail["sources"][number];

/**
 * 所有 ID 和时间均为固定测试值，保证快照、MSW 场景与后续切片在任意机器上可重复。
 * ID 使用合法 UUID v4，既能通过前端路径测试，也能直接用于未来后端契约测试。
 */
export const CAMERA_FIXTURE_IDS = {
  primaryCamera: "6f9619ff-8b86-4e4f-9f68-bb3f8f6f4f21",
  secondaryCamera: "72f04e18-29b8-4c63-a62f-3a4d59f84871",
  primarySource: "3f2504e0-4f89-41d3-9a0c-0305e82c3301",
  secondarySource: "8f14e45f-ea9d-4a7d-9b6d-8c9f0a1b2c3d",
  tertiarySource: "91b74192-2d6b-4f24-8d31-7706421f8751",
} as const;

export const CAMERA_FIXTURE_TIMES = {
  createdAt: "2026-08-19T03:00:00Z",
  updatedAt: "2026-08-19T03:10:00Z",
  checkedAt: "2026-08-19T03:10:01Z",
} as const;

export const CAMERA_FIXTURE_TRACE_ID = "tr_cameras_fixture_0001";

/** 此唯一哨兵贯穿后端与前端，只能存在于敏感详情和写请求 Fixture。 */
export const CAMERA_FIXTURE_SECRET = "cameras-mvp-leak-sentinel";

const DEFAULT_SOURCE_IDS = [
  CAMERA_FIXTURE_IDS.primarySource,
  CAMERA_FIXTURE_IDS.secondarySource,
  CAMERA_FIXTURE_IDS.tertiarySource,
] as const;

export interface CameraSourceFixtureInput {
  source_id?: string;
  name?: string;
  url_suffix?: string;
  status?: CameraSourceDetail["status"];
  error?: CameraSourceDetail["error"];
  whep_url?: string | null;
  last_checked_at?: string;
}

export interface CameraDetailFixtureOptions {
  cameraId?: string;
  name?: string;
  ipAddress?: string;
  rtspPort?: number;
  username?: string;
  password?: string;
  sources?: readonly CameraSourceFixtureInput[];
  defaultSourceIndex?: number;
  createdAt?: string;
  updatedAt?: string;
}

function fixtureSourceId(input: CameraSourceFixtureInput, index: number) {
  const sourceId = input.source_id ?? DEFAULT_SOURCE_IDS[index];
  if (sourceId === undefined) {
    throw new Error(
      `第 ${index + 1} 路 Fixture Source 必须显式提供 source_id。`,
    );
  }
  return sourceId;
}

function aggregateStatus(
  onlineSourceCount: number,
  sourceCount: number,
): CameraDetail["status"] {
  if (onlineSourceCount === sourceCount) {
    return "ONLINE";
  }
  return onlineSourceCount === 0 ? "OFFLINE" : "DEGRADED";
}

function encodeRtspComponent(value: string) {
  /**
   * encodeURIComponent 不编码 `!'()*`，而 Backend 使用 RFC 3986 的严格组件编码。额外处理这
   * 五个字符，确保 MSW 详情与真实 API 返回的 RTSP URL 完全一致。
   */
  return encodeURIComponent(value).replace(
    /[!'()*]/g,
    (character) => `%${character.charCodeAt(0).toString(16).toUpperCase()}`,
  );
}

function buildFixtureRtspUrl(
  username: string,
  password: string,
  ipAddress: string,
  rtspPort: number,
  urlSuffix: string,
) {
  /**
   * Source 后缀允许携带 query。Path 只保留 `/` 层级，query 只保留 `&` 和第一个 `=` 的
   * 参数结构；其他保留字符必须编码，否则 Fixture 会掩盖真实 API 已修复的裸拼接问题。
   */
  const querySeparatorIndex = urlSuffix.indexOf("?");
  const path =
    querySeparatorIndex === -1
      ? urlSuffix
      : urlSuffix.slice(0, querySeparatorIndex);
  const encodedPath = path.split("/").map(encodeRtspComponent).join("/");
  let encodedSuffix = encodedPath;

  if (querySeparatorIndex !== -1) {
    const query = urlSuffix.slice(querySeparatorIndex + 1);
    const encodedQuery = query
      .split("&")
      .map((pair) => {
        const valueSeparatorIndex = pair.indexOf("=");
        if (valueSeparatorIndex === -1) {
          return encodeRtspComponent(pair);
        }
        const name = pair.slice(0, valueSeparatorIndex);
        const value = pair.slice(valueSeparatorIndex + 1);
        return `${encodeRtspComponent(name)}=${encodeRtspComponent(value)}`;
      })
      .join("&");
    encodedSuffix = `${encodedPath}?${encodedQuery}`;
  }

  return (
    `rtsp://${encodeRtspComponent(username)}:${encodeRtspComponent(password)}` +
    `@${ipAddress}:${rtspPort}/${encodedSuffix}`
  );
}

/**
 * 构造始终满足 Camera 聚合不变量的敏感详情。
 *
 * 默认源、计数和聚合状态全部从 Source 输入派生，调用方不能通过互相矛盾的 override 制造一个
 * 看似合法的响应。这样后续 UI 测试若需要损坏聚合，必须建立名字明确的专用非法 Fixture。
 */
export function buildCameraDetail(
  options: CameraDetailFixtureOptions = {},
): CameraDetail {
  const cameraId = options.cameraId ?? CAMERA_FIXTURE_IDS.primaryCamera;
  const name = options.name ?? "洗手区 01";
  const ipAddress = options.ipAddress ?? "192.0.2.64";
  const rtspPort = options.rtspPort ?? 554;
  const username = options.username ?? "fixture-camera-user";
  const password = options.password ?? CAMERA_FIXTURE_SECRET;
  const sourceInputs = options.sources ?? [
    { name: "主码流", url_suffix: "Streaming/Channels/101", status: "ONLINE" },
    {
      name: "子码流",
      url_suffix: "Streaming/Channels/102",
      status: "OFFLINE",
      error: "MTX_PATH_NOT_FOUND",
      whep_url: null,
    },
  ];
  const defaultSourceIndex = options.defaultSourceIndex ?? 0;

  if (sourceInputs.length === 0) {
    throw new Error("Camera Fixture 至少需要一路 Source。");
  }
  if (defaultSourceIndex < 0 || defaultSourceIndex >= sourceInputs.length) {
    throw new Error(
      "Camera Fixture 的 defaultSourceIndex 必须指向现有 Source。",
    );
  }

  const sources = sourceInputs.map((input, index): CameraSourceDetail => {
    const sourceId = fixtureSourceId(input, index);
    const status = input.status ?? "ONLINE";
    const urlSuffix = input.url_suffix ?? `Streaming/Channels/${index + 1}01`;
    /**
     * Source 的派生值必须与状态保持一致：ONLINE 不携带错误，OFFLINE 未指定错误时使用稳定
     * 错误码。`whep_url: undefined` 表示让 Builder 按状态生成默认值，而显式 `null` 表示调用方
     * 正在构造“当前不可播放”的合法响应，不能被空值合并运算覆盖。
     */
    const defaultWhepUrl =
      status === "ONLINE"
        ? `https://media.example.invalid/${sourceId}/whep`
        : null;

    return {
      source_id: sourceId,
      name: input.name ?? `视频源 ${index + 1}`,
      url_suffix: urlSuffix,
      rtsp_url: buildFixtureRtspUrl(
        username,
        password,
        ipAddress,
        rtspPort,
        urlSuffix,
      ),
      is_default_preview: index === defaultSourceIndex,
      status,
      last_checked_at: input.last_checked_at ?? CAMERA_FIXTURE_TIMES.checkedAt,
      error: status === "ONLINE" ? null : (input.error ?? "MTX_PATH_NOT_FOUND"),
      whep_url: input.whep_url === undefined ? defaultWhepUrl : input.whep_url,
    };
  });
  const onlineSourceCount = sources.filter(
    (source) => source.status === "ONLINE",
  ).length;
  const defaultSource = sources[defaultSourceIndex];
  if (defaultSource === undefined) {
    // 前面的范围校验理论上已排除此分支；保留防御检查以适配 noUncheckedIndexedAccess。
    throw new Error("Camera Fixture 的默认 Source 不存在。");
  }

  return {
    camera_id: cameraId,
    name,
    ip_address: ipAddress,
    rtsp_port: rtspPort,
    username,
    password,
    default_preview_source_id: defaultSource.source_id,
    status: aggregateStatus(onlineSourceCount, sources.length),
    online_source_count: onlineSourceCount,
    source_count: sources.length,
    sources,
    created_at: options.createdAt ?? CAMERA_FIXTURE_TIMES.createdAt,
    updated_at: options.updatedAt ?? CAMERA_FIXTURE_TIMES.updatedAt,
  };
}

/** 通过逐字段投影构造非敏感摘要，禁止把详情新增字段意外扩散到列表。 */
export function buildCameraSummary(
  detail: CameraDetail = buildCameraDetail(),
): CameraSummary {
  const defaultSource = detail.sources.find(
    (source) => source.source_id === detail.default_preview_source_id,
  );
  if (defaultSource === undefined) {
    throw new Error("Camera Detail Fixture 的默认 Source 不存在。");
  }

  return {
    camera_id: detail.camera_id,
    name: detail.name,
    ip_address: detail.ip_address,
    rtsp_port: detail.rtsp_port,
    status: detail.status,
    online_source_count: detail.online_source_count,
    source_count: detail.source_count,
    default_preview_source: {
      source_id: defaultSource.source_id,
      name: defaultSource.name,
      status: defaultSource.status,
      last_checked_at: defaultSource.last_checked_at,
      whep_url: defaultSource.whep_url,
    },
    created_at: detail.created_at,
    updated_at: detail.updated_at,
  };
}

export interface CameraPageFixtureOptions {
  items?: CameraSummary[];
  page?: number;
  pageSize?: number;
  total?: number;
}

/** 构造仅包含非敏感 Camera Summary 的分页响应，默认 total 与实际 items 数量一致。 */
export function buildCameraPage(
  options: CameraPageFixtureOptions = {},
): CameraPage {
  const items = options.items ?? [buildCameraSummary()];
  return {
    items,
    page: options.page ?? 1,
    page_size: options.pageSize ?? 20,
    total: options.total ?? items.length,
  };
}

/**
 * 从敏感详情构造创建请求；凭据只允许进入写请求或详情，不得复用此结果作为列表响应。
 */
export function buildCameraCreateRequest(
  detail: CameraDetail = buildCameraDetail(),
): CameraCreateRequest {
  return {
    name: detail.name,
    ip_address: detail.ip_address,
    rtsp_port: detail.rtsp_port,
    username: detail.username,
    password: detail.password,
    sources: detail.sources.map((source) => ({
      name: source.name,
      url_suffix: source.url_suffix,
      is_default_preview: source.is_default_preview,
    })),
  };
}

/**
 * 构造保留既有 Source ID 的更新请求，用于验证更新契约而非服务端只读状态字段。
 * 与创建请求相同，该对象会携带凭据，只能用于写请求 Fixture。
 */
export function buildCameraUpdateRequest(
  detail: CameraDetail = buildCameraDetail(),
): CameraUpdateRequest {
  return {
    ...buildCameraCreateRequest(detail),
    sources: detail.sources.map((source) => ({
      source_id: source.source_id,
      name: source.name,
      url_suffix: source.url_suffix,
      is_default_preview: source.is_default_preview,
    })),
  };
}

/** 逐字段投影默认预览源写操作的响应，防止敏感 Camera Detail 字段意外泄漏。 */
export function buildDefaultPreviewSourceResponse(
  detail: CameraDetail = buildCameraDetail(),
): DefaultPreviewSourceResponse {
  return {
    camera_id: detail.camera_id,
    default_preview_source_id: detail.default_preview_source_id,
    updated_at: detail.updated_at,
  };
}

/** 构造可用的 WHEP 播放信息；URL 使用保留测试域名，避免测试误连真实媒体服务。 */
export function buildPlaybackInfo(
  sourceId: string = CAMERA_FIXTURE_IDS.primarySource,
): PlaybackInfo {
  return {
    source_id: sourceId,
    protocol: "WHEP",
    url: `https://media.example.invalid/${sourceId}/whep`,
    status: "AVAILABLE",
    expires_at: null,
  };
}

export interface ProblemFixtureOptions {
  status: number;
  code: string;
  instance: string;
  type?: string;
  title?: string;
  detail?: string;
  traceId?: string;
  errors?: ProblemDetails["errors"];
  context?: NonNullable<ProblemDetails["context"]>;
}

/**
 * 构造符合项目 Problem Details 扩展契约的错误 body。
 * 响应媒体类型、HTTP 状态和 Trace Header 由场景层补齐并保持一致。
 */
export function buildProblem(options: ProblemFixtureOptions): ProblemDetails {
  return {
    type:
      options.type ??
      `urn:sop-vision:problem:${options.code.toLowerCase().replaceAll("_", "-")}`,
    title: options.title ?? "请求未能完成",
    status: options.status,
    code: options.code,
    detail: options.detail ?? "请稍后重试或修正请求后再试。",
    instance: options.instance,
    trace_id: options.traceId ?? CAMERA_FIXTURE_TRACE_ID,
    errors: options.errors ?? [],
    context: options.context ?? {},
  };
}
