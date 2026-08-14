# SOP Vision FastAPI 接口设计 v1

> 文档状态：接口设计草案，可用于前后端联调评审，不代表需求已冻结  
> 更新日期：2026-08-14  
> API 前缀：`/api/v1`  
> 需求基线：[sop-vision-prd-v1.4.md](./sop-vision-prd-v1.4.md)  
> 产品基线：[detector-requirements-and-prototype.md](./detector-requirements-and-prototype.md)  
> 交互原型：[prototype/v1.4.html](./prototype/v1.4.html)  
> 架构基线：[vision-platform-architecture.md](./vision-platform-architecture.md)

## 1. 文档目标

本文把需求与 v1.4 原型中的页面操作转换为 FastAPI 层的 HTTP/WebSocket 合约，供前端、FastAPI、Detector 和测试共同评审。

本期接口覆盖：

- Camera 与 CameraSource 的查询、创建、编辑和默认预览源切换。
- CameraSource 播放信息获取。
- Algorithm 只读目录、动态参数 schema 与 ROI 定义查询。
- DetectionTask 的查询、创建、编辑和删除。
- DetectionTask 的启动、停止、重载、重启及命令状态查询。
- DetectionTask Actual State、实时检测数据和错误信息推送。
- FastAPI 存活与就绪检查。

本期不提供：

- Camera 删除接口。
- Algorithm 创建、编辑和删除接口。
- 历史检测结果、异常事件、证据视频和测试运行接口。
- 用户、角色、权限和审计管理接口。
- MediaMTX、Redis、PostgreSQL 或 Detector gRPC 的直通接口。

## 2. 设计状态说明

本文使用以下标记区分需求结论与接口设计选择：

| 标记 | 含义 |
| --- | --- |
| 已明确 | 需求或原型已经给出唯一业务语义 |
| 设计暂定 | 为形成可联调接口而作出的可替换技术选择，仍需产品或架构确认 |
| 安全例外 | 需求明确要求，但与通常的生产安全实践冲突，上线前必须再次评审 |

主要暂定项：

1. Actual State 暂采用 `UNKNOWN / STARTING / RUNNING / RECONNECTING / DEGRADED / STOPPING / STOPPED / ERROR`。
2. 运行命令采用异步 `202 Accepted`，由命令资源反馈最终结果。
3. 运行中或 `enabled = true` 的任务暂不允许删除，调用方需要先停止任务。
4. 离线 CameraSource 允许创建任务，但启动任务时暂返回 `409 SOURCE_UNAVAILABLE`。
5. Camera IP 暂按 IPv4 接收；IPv6、主机名和域名支持待 Q-06 确认。
6. 身份体系尚未定义；接口预留 Bearer/会话认证及 `401/403`，不得据此认为匿名访问已获准。
7. ROI 坐标采用需求基线中明确的归一化坐标，原点为视频内容左上角，范围 `[0, 1]`。

## 3. 总体约定

### 3.1 协议与媒体类型

- REST 使用 HTTPS；本地开发可以使用 HTTP。
- 请求和成功响应使用 `application/json`。
- 错误响应使用 `application/problem+json`。
- 实时数据使用 WebSocket 文本帧，每帧为一个 UTF-8 JSON 对象。
- 浏览器视频不经过 FastAPI；FastAPI 只返回 MediaMTX 播放地址。

### 3.2 字段命名、ID 和时间

- JSON 字段统一使用 `snake_case`。
- `camera_id`、`source_id`、`task_id`、`command_id` 由服务端生成，调用方将其视为不透明、不可变字符串。
- 文档示例使用 `cam_01J...`、`src_01J...` 等可读前缀，不要求前端解析前缀。
- 时间使用 RFC 3339 UTC 字符串，例如 `2026-08-14T06:20:00.123Z`。
- 检测帧协议为了降低体积，继续使用 UTC Unix 毫秒字段 `frame_ts_ms` 和 `published_at_ms`。
- 枚举值使用大写字符串；面向用户的中文文案由前端映射，不能依赖后端文案判断状态。

### 3.3 鉴权与权限

身份与角色尚未冻结。接口先保留以下行为：

- REST 请求使用 `Authorization: Bearer <token>` 或同源安全会话 Cookie，最终方式待认证方案确定。
- 无有效身份返回 `401 AUTHENTICATION_REQUIRED`。
- 无资源权限返回 `403 PERMISSION_DENIED`，不由前端仅靠隐藏按钮代替授权。
- WebSocket 优先使用同源 `HttpOnly` 会话 Cookie；若最终使用 Bearer Token，应另行设计短期 WebSocket ticket，不在 URL 中长期暴露访问令牌。

开发环境若暂时关闭认证，OpenAPI 中仍应保留安全方案定义和上述错误响应。

### 3.4 分页、搜索和排序

列表接口统一支持：

| 参数 | 类型 | 默认值 | 约束 | 说明 |
| --- | --- | --- | --- | --- |
| `page` | integer | `1` | `>= 1` | 页码 |
| `page_size` | integer | `20` | `1–100` | 每页数量 |
| `q` | string | 无 | 去除首尾空白，最长 100 | 模糊搜索 |
| `sort` | string | 各接口定义 | 白名单 | `field` 升序，`-field` 降序 |

分页响应：

```json
{
  "items": [],
  "page": 1,
  "page_size": 20,
  "total": 0
}
```

当 `total = 0` 时，前端根据 `q` 是否为空区分“系统无数据”和“搜索无结果”。

### 3.5 并发修改

Camera 和 DetectionTask 资源返回：

- JSON 字段 `revision`。
- HTTP 响应头 `ETag: "<revision>"`。

更新、切换默认源和删除请求必须携带：

```http
If-Match: "7"
```

版本不一致返回 `412 REVISION_MISMATCH`，并在错误 `context.current_revision` 中提供最新版本。前端应提示“配置已被其他操作修改”，重新读取后再允许用户覆盖。

`revision` 用于 HTTP 并发控制；DetectionTask 的 `config_version` 用于 Desired Config 与 Detector Applied Config 对账，两者含义不同。

### 3.6 幂等与异步命令

创建资源和运行命令支持：

```http
Idempotency-Key: <UUID or opaque string>
```

- 同一身份、同一路径、同一 key 和相同请求体重复提交，返回第一次调用的结果。
- 同一 key 携带不同请求体返回 `409 IDEMPOTENCY_KEY_REUSED`。
- 前端对启动、停止、重载、重启必须生成并复用该 key，避免网络重试产生重复命令。
- 幂等记录保留时长暂定 24 小时。

### 3.7 通用错误模型

错误响应采用 Problem Details 风格，并增加稳定的业务错误码和字段错误：

```json
{
  "type": "https://sop-vision.local/problems/validation-error",
  "title": "Request validation failed",
  "status": 422,
  "detail": "One or more fields are invalid.",
  "instance": "/api/v1/detection-tasks",
  "code": "VALIDATION_ERROR",
  "trace_id": "tr_01J5...",
  "errors": [
    {
      "field": "rois[0].points",
      "code": "ROI_TOO_FEW_POINTS",
      "message": "ROI 至少需要 3 个顶点。"
    }
  ],
  "context": {}
}
```

稳定字段为 `status`、`code`、`errors[].field` 和 `errors[].code`。`title`、`detail`、`message` 可本地化，前端不得据此编写业务分支。

通用状态码：

| HTTP | 场景 |
| --- | --- |
| `400` | JSON 语义或查询组合无效 |
| `401` | 未认证 |
| `403` | 无权限 |
| `404` | 资源不存在 |
| `409` | 引用冲突、状态冲突、命令冲突或幂等冲突 |
| `412` | `If-Match` 与当前 `revision` 不一致 |
| `422` | 字段、算法参数或 ROI 校验失败 |
| `429` | 请求或 WebSocket 连接超限 |
| `502` | MediaMTX 或 Detector 控制服务返回无效响应 |
| `503` | 必需依赖暂不可用 |
| `504` | 下游控制调用超时 |

## 4. 核心资源模型

### 4.1 Camera 与 CameraSource

```text
Camera 1 ── N CameraSource
Camera.default_preview_source_id ── 1 CameraSource
CameraSource 1 ── N DetectionTask
```

Camera 是聚合根。创建和编辑弹窗一次提交 Camera 基础信息与完整 CameraSource 集合，服务端在一个数据库事务内保证：

- 至少存在一路 CameraSource。
- 恰好一路 `is_default_preview = true`。
- `source_id` 稳定，增删或排序不会改变任务绑定。
- 被 DetectionTask 引用的 CameraSource 不允许通过 Camera 编辑删除。

CameraSource 运行状态暂定：

| 值 | 含义 |
| --- | --- |
| `UNKNOWN` | 尚未探测或运行时状态已过期 |
| `ONLINE` | 可连接且状态正常 |
| `DEGRADED` | 可用但存在丢帧、重连或其他异常 |
| `OFFLINE` | 当前不可连接 |

Camera 聚合状态由所有源计算：全部 `OFFLINE` 为 `OFFLINE`；全部 `ONLINE` 为 `ONLINE`；其他组合为 `DEGRADED`；无有效运行时数据为 `UNKNOWN`。

### 4.2 Algorithm

Algorithm 在本期是只读目录。一个具体可用算法由 `(algorithm_id, version)` 唯一标识，并向任务表单提供：

- 名称和版本。
- 参数定义及默认值。
- ROI 定义的 `roi_id`、标签和顺序。

前端不能把原型中的算法清单硬编码为生产配置。

### 4.3 DetectionTask

DetectionTask 保存 Desired Config：

- 名称与描述。
- 唯一绑定的 `source_id`。
- 唯一绑定的 `algorithm_id` 与 `algorithm_version`。
- 经算法 schema 校验后的 `parameters`。
- 算法要求的完整 ROI 集合。
- 期望运行状态 `enabled`。
- 单调递增的 `config_version`。

Redis/Detector 提供 Actual State：

- `runtime.state`。
- `runtime.applied_config_version`。
- `runtime.last_heartbeat_at`。
- FPS、推理延迟和最近错误。

`enabled` 和 `runtime.state` 必须独立返回，不能由其中一项推导另一项。

## 5. 接口总览

| 模块 | 方法 | 路径 | 作用 |
| --- | --- | --- | --- |
| Health | GET | `/health/live` | FastAPI 进程存活检查 |
| Health | GET | `/health/ready` | 关键依赖就绪检查 |
| Cameras | GET | `/cameras` | Camera 卡片列表与搜索 |
| Cameras | POST | `/cameras` | 创建 Camera 及多路源 |
| Cameras | GET | `/cameras/{camera_id}` | Camera 详情 |
| Cameras | PUT | `/cameras/{camera_id}` | 原子更新 Camera 及完整源集合 |
| Cameras | PATCH | `/cameras/{camera_id}/default-preview-source` | 切换默认预览源 |
| Cameras | GET | `/cameras/{camera_id}/sources` | 获取不含凭据的源选择列表 |
| Playback | GET | `/camera-sources/{source_id}/playback` | 获取 MediaMTX 播放信息 |
| Algorithms | GET | `/algorithms` | 获取可选算法列表 |
| Algorithms | GET | `/algorithms/{algorithm_id}/versions/{version}` | 获取参数与 ROI schema |
| Tasks | GET | `/detection-tasks` | 任务列表、搜索与过滤 |
| Tasks | POST | `/detection-tasks` | 创建默认停止的任务 |
| Tasks | GET | `/detection-tasks/{task_id}` | 任务详情与当前运行状态 |
| Tasks | PUT | `/detection-tasks/{task_id}` | 更新任务配置，不改变 `enabled` |
| Tasks | DELETE | `/detection-tasks/{task_id}` | 删除已停止任务 |
| Commands | POST | `/detection-tasks/{task_id}/commands` | 启动、停止、重载或重启 |
| Commands | GET | `/detection-task-commands/{command_id}` | 查询异步命令结果 |
| Realtime | WS | `/ws/detection-tasks/{task_id}` | 实时状态与检测帧 |

完整 URL 示例：`https://vision.example.internal/api/v1/cameras`。

## 6. Health 接口

### 6.1 存活检查

```http
GET /api/v1/health/live
```

`200`：

```json
{
  "status": "ok"
}
```

只判断 FastAPI 进程能否响应，不检查外部依赖。

### 6.2 就绪检查

```http
GET /api/v1/health/ready
```

`200`：

```json
{
  "status": "ok",
  "dependencies": {
    "postgres": "ok",
    "redis": "ok",
    "mediamtx": "ok"
  }
}
```

PostgreSQL 等配置事实源不可用时返回 `503 NOT_READY`。Redis、MediaMTX 和 Detector 的就绪等级需结合部署探针策略确定；其中 Detector/Worker 不应成为 FastAPI 管理面是否就绪的硬条件，否则 Detector 故障会使 Camera 配置 API 一并退出负载均衡。当前代码把 MediaMTX 作为就绪条件，若要让 Redis/MediaMTX 故障时配置 REST API 继续服务，需要在实现阶段将“进程就绪”和“依赖健康明细”拆开。

## 7. Cameras 接口

### 7.1 Camera 列表

```http
GET /api/v1/cameras?q=洗手&page=1&page_size=20&sort=name
```

`q` 匹配 Camera 名称或 IP。默认 `sort=name`，可用排序：`name`、`-name`、`created_at`、`-created_at`。

`200`：

```json
{
  "items": [
    {
      "camera_id": "cam_01J5WASH01",
      "name": "洗手区 01",
      "ip_address": "192.168.1.64",
      "rtsp_port": 554,
      "status": "ONLINE",
      "online_source_count": 2,
      "source_count": 2,
      "detection_task_count": 2,
      "default_preview_source": {
        "source_id": "src_01J5MAIN01",
        "name": "通道 1 主码流",
        "status": "ONLINE"
      },
      "revision": 7,
      "updated_at": "2026-08-14T06:20:00Z"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

列表不返回密码和完整 RTSP URL。卡片加载预览时再调用播放接口。

### 7.2 创建 Camera

```http
POST /api/v1/cameras
Idempotency-Key: 32d1bc57-1977-4d8a-97f8-bda387ea0958
Content-Type: application/json
```

请求：

```json
{
  "name": "洗手区 01",
  "ip_address": "192.168.1.64",
  "rtsp_port": 554,
  "username": "admin",
  "password": "hikvision123",
  "sources": [
    {
      "name": "通道 1 主码流",
      "url_suffix": "Streaming/Channels/101",
      "is_default_preview": true
    },
    {
      "name": "通道 1 子码流",
      "url_suffix": "/Streaming/Channels/102",
      "is_default_preview": false
    }
  ]
}
```

服务端去除 `url_suffix` 开头的所有 `/`。成功返回 `201 Created`、`Location: /api/v1/cameras/{camera_id}` 和 CameraDetail。

核心校验：

| 字段 | 规则 | 错误码 |
| --- | --- | --- |
| `name` | 去除首尾空白后必填，暂定最长 128 | `REQUIRED` / `STRING_TOO_LONG` |
| `ip_address` | 必填，设计暂定 IPv4 | `INVALID_IP_ADDRESS` |
| `rtsp_port` | `1–65535`，前端新建默认 554 | `OUT_OF_RANGE` |
| `username` | 必填，暂定最长 128 | `REQUIRED` |
| `password` | 必填，暂定最长 512 | `REQUIRED` |
| `sources` | 至少一项 | `SOURCE_REQUIRED` |
| `sources[].name` | 必填，暂定最长 128 | `REQUIRED` |
| `sources[].url_suffix` | 规范化后必填，暂定最长 1024 | `REQUIRED` |
| `is_default_preview` | 恰好一项为 `true` | `DEFAULT_SOURCE_REQUIRED` / `MULTIPLE_DEFAULT_SOURCES` |

Camera 名称、IP 与 URL 后缀的唯一性未冻结。第一版仅建议对同一 Camera 内规范化后的重复 `url_suffix` 返回 `422 DUPLICATE_SOURCE_SUFFIX`，数据库暂不强制 Camera 名称或 IP 全局唯一。

### 7.3 Camera 详情

```http
GET /api/v1/cameras/cam_01J5WASH01
```

`200`：

```json
{
  "camera_id": "cam_01J5WASH01",
  "name": "洗手区 01",
  "ip_address": "192.168.1.64",
  "rtsp_port": 554,
  "username": "admin",
  "password": "hikvision123",
  "default_preview_source_id": "src_01J5MAIN01",
  "status": "DEGRADED",
  "online_source_count": 1,
  "source_count": 2,
  "detection_task_count": 2,
  "sources": [
    {
      "source_id": "src_01J5MAIN01",
      "name": "通道 1 主码流",
      "url_suffix": "Streaming/Channels/101",
      "rtsp_url": "rtsp://admin:hikvision123@192.168.1.64:554/Streaming/Channels/101",
      "is_default_preview": true,
      "status": "ONLINE",
      "last_checked_at": "2026-08-14T06:19:58Z",
      "error": null,
      "detection_task_count": 2
    },
    {
      "source_id": "src_01J5SUB01",
      "name": "通道 1 子码流",
      "url_suffix": "Streaming/Channels/102",
      "rtsp_url": "rtsp://admin:hikvision123@192.168.1.64:554/Streaming/Channels/102",
      "is_default_preview": false,
      "status": "DEGRADED",
      "last_checked_at": "2026-08-14T06:19:57Z",
      "error": {
        "code": "PACKET_LOSS",
        "message": "视频流丢包率过高。"
      },
      "detection_task_count": 0
    }
  ],
  "revision": 7,
  "created_at": "2026-08-01T03:00:00Z",
  "updated_at": "2026-08-14T06:20:00Z"
}
```

安全例外：需求基线要求详情 API 原样返回用户名、密码和完整 RTSP URL。该响应不得进入共享缓存，必须设置 `Cache-Control: no-store`，并在生产上线前完成访问控制和凭据方案复审。

### 7.4 更新 Camera 与源集合

```http
PUT /api/v1/cameras/cam_01J5WASH01
If-Match: "7"
Content-Type: application/json
```

请求体与创建相同，但已有源携带 `source_id`，新源不携带 `source_id`：

```json
{
  "name": "洗手区 01",
  "ip_address": "192.168.1.64",
  "rtsp_port": 554,
  "username": "admin",
  "password": "new-password",
  "sources": [
    {
      "source_id": "src_01J5MAIN01",
      "name": "通道 1 主码流",
      "url_suffix": "Streaming/Channels/101",
      "is_default_preview": true
    },
    {
      "name": "通道 2 主码流",
      "url_suffix": "Streaming/Channels/201",
      "is_default_preview": false
    }
  ]
}
```

语义：

- 请求中的 `sources` 是保存后的完整集合，不是局部补丁。
- 已存在但未出现在请求中的源视为删除。
- 请求中的 `source_id` 必须属于当前 Camera，否则返回 `422 SOURCE_NOT_OWNED_BY_CAMERA`。
- 删除被任务引用的源返回 `409 SOURCE_IN_USE`，`context.references` 返回关联任务的 ID 与名称。
- 整个修改必须在一个事务内完成；任一源失败时 Camera 基础字段也不得部分保存。
- 更新成功返回 `200` CameraDetail 和新 `ETag`。

CameraSource 凭据由 Camera 统一维护。修改 IP、端口、用户名或密码时，所有源的生成 RTSP URL 一并变化。

### 7.5 切换默认预览源

```http
PATCH /api/v1/cameras/cam_01J5WASH01/default-preview-source
If-Match: "8"
Content-Type: application/json

{
  "source_id": "src_01J5SUB01"
}
```

成功返回 `200`：

```json
{
  "camera_id": "cam_01J5WASH01",
  "default_preview_source_id": "src_01J5SUB01",
  "revision": 9,
  "updated_at": "2026-08-14T06:25:00Z"
}
```

该操作只改变 Cameras 的默认预览，不修改任何 DetectionTask 的 `source_id`。

### 7.6 获取 CameraSource 选择列表

```http
GET /api/v1/cameras/cam_01J5WASH01/sources
```

`200`：

```json
{
  "items": [
    {
      "source_id": "src_01J5MAIN01",
      "name": "通道 1 主码流",
      "is_default_preview": true,
      "status": "ONLINE",
      "last_checked_at": "2026-08-14T06:19:58Z",
      "detection_task_count": 2
    },
    {
      "source_id": "src_01J5SUB01",
      "name": "通道 1 子码流",
      "is_default_preview": false,
      "status": "DEGRADED",
      "last_checked_at": "2026-08-14T06:19:57Z",
      "detection_task_count": 0
    }
  ]
}
```

该接口供 DetectionTask 的两级 Camera/CameraSource 选择器使用，不返回用户名、密码、URL 后缀或完整 RTSP URL，避免任务表单为了列出源而读取 Camera 凭据。

### 7.7 获取播放信息

```http
GET /api/v1/camera-sources/src_01J5MAIN01/playback
```

`200`：

```json
{
  "source_id": "src_01J5MAIN01",
  "protocol": "WHEP",
  "url": "https://vision.example.internal/media/wash-01-main/whep",
  "status": "ONLINE",
  "expires_at": null
}
```

说明：

- FastAPI 返回对外可访问的 MediaMTX URL，前端直接与 MediaMTX 建立播放会话。
- “开始/停止预览”是浏览器本地播放控制，不新增后端启停接口，也不改变 CameraSource 或 DetectionTask 状态。
- 源不存在返回 `404 SOURCE_NOT_FOUND`。
- MediaMTX 路径尚未对账成功返回 `409 PLAYBACK_NOT_READY`。
- MediaMTX 不可用返回 `503 MEDIA_SERVICE_UNAVAILABLE`。

## 8. Algorithms 接口

### 8.1 Algorithm 列表

```http
GET /api/v1/algorithms?q=人员&status=ACTIVE&page=1&page_size=100
```

查询参数：

- `q` 匹配算法名称或 `algorithm_id`。
- `status` 暂支持 `ACTIVE`、`DEPRECATED`，任务新建页只请求 `ACTIVE`。

`200`：

```json
{
  "items": [
    {
      "algorithm_id": "region-person-detection",
      "name": "区域人员检测",
      "latest_version": "2.1.0",
      "status": "ACTIVE",
      "available_versions": ["2.1.0"]
    }
  ],
  "page": 1,
  "page_size": 100,
  "total": 1
}
```

原型中的三个算法仅为接口示例，不视为首批正式目录。

### 8.2 Algorithm 版本详情

```http
GET /api/v1/algorithms/region-person-detection/versions/2.1.0
```

`200`：

```json
{
  "algorithm_id": "region-person-detection",
  "name": "区域人员检测",
  "version": "2.1.0",
  "status": "ACTIVE",
  "parameter_definitions": [
    {
      "key": "confidence",
      "label": "置信度阈值",
      "type": "NUMBER",
      "required": true,
      "default": 0.55,
      "minimum": 0,
      "maximum": 1,
      "step": 0.05,
      "unit": null
    },
    {
      "key": "tracking_mode",
      "label": "跟踪模式",
      "type": "SELECT",
      "required": true,
      "default": "balanced",
      "options": [
        {"value": "fast", "label": "快速"},
        {"value": "balanced", "label": "均衡"},
        {"value": "accurate", "label": "精确"}
      ]
    },
    {
      "key": "enabled_feature",
      "label": "启用特性",
      "type": "BOOLEAN",
      "required": true,
      "default": true
    }
  ],
  "roi_definitions": [
    {"roi_id": "washing_area", "label": "洗手池监测区", "required": true, "order": 1},
    {"roi_id": "sanitizing_area", "label": "消毒监测区", "required": true, "order": 2}
  ]
}
```

当前 schema 类型仅冻结原型已使用的 `NUMBER / SELECT / BOOLEAN`。增加字符串、数组、条件字段或跨字段约束时需要升级接口文档，并保证旧版本算法 schema 仍可读取。

## 9. Detection Tasks 接口

### 9.1 任务列表

```http
GET /api/v1/detection-tasks?q=洗手&camera_id=cam_01J5WASH01&runtime_state=RUNNING&page=1&page_size=20&sort=-updated_at
```

筛选参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `q` | string | 匹配任务名称、描述、任务 ID、Camera 名称、源名称、算法名称或算法 ID |
| `camera_id` | string | 指定 Camera |
| `source_id` | string | 指定 CameraSource |
| `algorithm_id` | string | 指定 Algorithm |
| `enabled` | boolean | 期望运行状态 |
| `runtime_state` | enum | Actual State |

`200`：

```json
{
  "items": [
    {
      "task_id": "task_01J5PERSON01",
      "name": "区域人员检测",
      "description": "一楼洗手区早班人员停留检测",
      "source": {
        "source_id": "src_01J5MAIN01",
        "name": "通道 1 主码流",
        "status": "ONLINE",
        "camera_id": "cam_01J5WASH01",
        "camera_name": "洗手区 01"
      },
      "algorithm": {
        "algorithm_id": "region-person-detection",
        "name": "区域人员检测",
        "version": "2.1.0"
      },
      "enabled": true,
      "runtime_state": "RUNNING",
      "config_version": 4,
      "applied_config_version": 4,
      "revision": 10,
      "updated_at": "2026-08-14T06:20:00Z"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

运行时 key 过期或 Redis 不可用时，配置列表仍返回，`runtime_state` 为 `UNKNOWN`、`applied_config_version` 为 `null`，不能用陈旧状态永久显示“运行中”。

### 9.2 创建任务

```http
POST /api/v1/detection-tasks
Idempotency-Key: b4794168-354f-49ce-bd37-40238253ec4e
Content-Type: application/json
```

请求：

```json
{
  "name": "区域人员检测",
  "description": "一楼洗手区早班人员停留检测",
  "source_id": "src_01J5MAIN01",
  "algorithm_id": "region-person-detection",
  "algorithm_version": "2.1.0",
  "parameters": {
    "confidence": 0.55,
    "min_stay_seconds": 2,
    "tracking_mode": "balanced"
  },
  "rois": [
    {
      "roi_id": "washing_area",
      "points": [
        {"x": 0.08, "y": 0.12},
        {"x": 0.48, "y": 0.09},
        {"x": 0.45, "y": 0.49},
        {"x": 0.10, "y": 0.52}
      ]
    },
    {
      "roi_id": "sanitizing_area",
      "points": [
        {"x": 0.56, "y": 0.10},
        {"x": 0.91, "y": 0.15},
        {"x": 0.88, "y": 0.49}
      ]
    }
  ]
}
```

`201 Created` 返回 DetectionTaskDetail，并保证：

```json
{
  "enabled": false,
  "runtime": {
    "state": "STOPPED",
    "applied_config_version": null
  },
  "config_version": 1
}
```

服务端不得接受创建请求中的 `enabled` 或 Actual State。新任务必须由用户进入详情后手动启动。

核心校验：

| 规则 | 错误码 |
| --- | --- |
| 名称必填，暂定最长 128 | `REQUIRED` / `STRING_TOO_LONG` |
| 描述最长 100 个字符 | `STRING_TOO_LONG` |
| `source_id` 必须存在 | `SOURCE_NOT_FOUND` |
| 算法版本必须存在且可用于新任务 | `ALGORITHM_VERSION_NOT_FOUND` / `ALGORITHM_DEPRECATED` |
| 参数 key、类型、必填、范围和枚举必须符合 schema | `UNKNOWN_PARAMETER` / `INVALID_PARAMETER_TYPE` / `PARAMETER_OUT_OF_RANGE` / `INVALID_PARAMETER_OPTION` |
| ROI ID 集合必须与算法要求一致 | `MISSING_REQUIRED_ROI` / `UNKNOWN_ROI` / `DUPLICATE_ROI` |
| 每个 ROI 至少 3 个点 | `ROI_TOO_FEW_POINTS` |
| 每个 `x/y` 在 `[0,1]` | `ROI_POINT_OUT_OF_BOUNDS` |

多边形自相交、重复点、重叠和最小面积尚未冻结，第一版不应在未评审时擅自拒绝；可先记录可观测警告。

离线源允许保存。成功响应可附加非阻断警告：

```json
{
  "meta": {
    "warnings": [
      {
        "code": "SOURCE_CURRENTLY_OFFLINE",
        "message": "当前视频源离线，任务保存后仍为停止状态。"
      }
    ]
  }
}
```

`meta` 与 DetectionTaskDetail 的资源字段位于同一响应对象；无警告时返回 `"meta": {"warnings": []}`。不使用 HTTP `Warning` 头，避免浏览器端需要额外解析两套协议。

### 9.3 任务详情

```http
GET /api/v1/detection-tasks/task_01J5PERSON01
```

`200`：

```json
{
  "task_id": "task_01J5PERSON01",
  "name": "区域人员检测",
  "description": "一楼洗手区早班人员停留检测",
  "source": {
    "source_id": "src_01J5MAIN01",
    "name": "通道 1 主码流",
    "status": "ONLINE",
    "camera_id": "cam_01J5WASH01",
    "camera_name": "洗手区 01"
  },
  "algorithm": {
    "algorithm_id": "region-person-detection",
    "name": "区域人员检测",
    "version": "2.1.0"
  },
  "parameters": {
    "confidence": 0.55,
    "min_stay_seconds": 2,
    "tracking_mode": "balanced"
  },
  "rois": [
    {
      "roi_id": "washing_area",
      "label": "洗手池监测区",
      "display_color": "#5AA7FF",
      "points": [
        {"x": 0.08, "y": 0.12},
        {"x": 0.48, "y": 0.09},
        {"x": 0.45, "y": 0.49}
      ]
    }
  ],
  "enabled": true,
  "runtime": {
    "state": "RUNNING",
    "applied_config_version": 4,
    "last_heartbeat_at": "2026-08-14T06:20:00Z",
    "fps": 24.7,
    "inference_ms": 18.4,
    "error": null,
    "active_command_id": null
  },
  "config_version": 4,
  "config_state": "APPLIED",
  "revision": 10,
  "created_at": "2026-08-01T03:00:00Z",
  "updated_at": "2026-08-14T06:20:00Z"
}
```

`config_state` 为派生值：

| 值 | 条件 |
| --- | --- |
| `NOT_APPLICABLE` | 任务停止且从未应用 |
| `APPLIED` | `config_version == applied_config_version` |
| `PENDING` | Desired 版本大于 Applied 版本且尚无失败结论 |
| `FAILED` | 最近一次应用该版本明确失败 |
| `UNKNOWN` | 运行时状态缺失，无法比较 |

任务详情页的视频播放仍调用绑定源的 `/camera-sources/{source_id}/playback`。

### 9.4 更新任务配置

```http
PUT /api/v1/detection-tasks/task_01J5PERSON01
If-Match: "10"
Content-Type: application/json
```

请求体字段与创建相同。更新语义：

- 完整替换名称、描述、绑定源、算法版本、参数和 ROI。
- 不接受 `enabled`、Actual State、`config_version` 或 `applied_config_version`。
- 成功后 `config_version + 1`，`revision + 1`。
- 无论任务当前是否运行，都不自动启动、停止、重载或重启。
- 运行中任务更新后，若 Detector 仍应用旧版本，则 `config_state = PENDING`，用户可显式点击“重载”。

成功返回 `200` DetectionTaskDetail。该语义解决“编辑不改变运行状态”，同时避免保存动作暗中修改运行实例。

### 9.5 删除任务

```http
DELETE /api/v1/detection-tasks/task_01J5PERSON01
If-Match: "11"
```

设计暂定规则：

- 仅当 `enabled = false` 且 Actual State 为 `STOPPED` 或 `UNKNOWN` 时允许删除。
- `enabled = true` 返回 `409 TASK_MUST_BE_STOPPED`。
- 已有启动/停止/重载/重启命令未结束时返回 `409 COMMAND_IN_PROGRESS`。
- 成功返回 `204 No Content`。
- 删除配置后 Camera 列表的关联任务数在同一数据库事务中自然更新，不单独调用“刷新计数”接口。

Camera 删除不在本期范围，因此没有对应 `DELETE /cameras/{camera_id}`。

## 10. Detection Task 命令接口

### 10.1 提交命令

```http
POST /api/v1/detection-tasks/task_01J5PERSON01/commands
Idempotency-Key: a591dc9d-65e8-46d8-906a-c3e6320901c0
Content-Type: application/json

{
  "action": "RELOAD"
}
```

`action`：

| Action | 前置条件 | 对 Desired State 的影响 | Detector 语义 |
| --- | --- | --- | --- |
| `START` | `enabled = false`；源可用 | 持久化 `enabled = true` | 使用当前保存配置启动 |
| `STOP` | `enabled = true` 或实例尚未停止 | 持久化 `enabled = false` | 真正停止任务 |
| `RELOAD` | `enabled = true` | 不变 | 保持任务进程和视频连接，载入当前配置 |
| `RESTART` | `enabled = true` | 不变 | 停止当前算法实例和视频连接，再用当前配置启动 |

接受后返回 `202 Accepted`：

```json
{
  "command_id": "cmd_01J5RELOAD01",
  "task_id": "task_01J5PERSON01",
  "action": "RELOAD",
  "status": "PENDING",
  "requested_config_version": 5,
  "requested_at": "2026-08-14T06:30:00Z",
  "started_at": null,
  "completed_at": null,
  "result": null,
  "error": null
}
```

同时返回：

```http
Location: /api/v1/detection-task-commands/cmd_01J5RELOAD01
Retry-After: 1
```

命令状态：`PENDING / RUNNING / SUCCEEDED / FAILED / TIMED_OUT / CANCELLED`。

冲突规则：

| 场景 | HTTP / code |
| --- | --- |
| 停止任务执行 RELOAD/RESTART | `409 TASK_NOT_ENABLED` |
| 启动时源离线（设计暂定） | `409 SOURCE_UNAVAILABLE` |
| 同一任务已有互斥命令 | `409 COMMAND_IN_PROGRESS`，返回现有 `command_id` |
| START 已达到“enabled=true 且 RUNNING” | 可返回 `200` 幂等完成结果，不创建新命令 |
| STOP 已达到“enabled=false 且 STOPPED” | 可返回 `200` 幂等完成结果，不创建新命令 |
| Detector 控制面不可用 | 若命令可排队则仍 `202`；若不能可靠排队则 `503 DETECTOR_UNAVAILABLE` |

START/STOP 修改 `enabled` 的事务边界与命令投递必须采用 outbox 或等价可靠机制，避免数据库已更新但命令永久丢失。Detector 的最终 Actual State 仍通过状态对账决定。

### 10.2 查询命令

```http
GET /api/v1/detection-task-commands/cmd_01J5RELOAD01
```

成功完成示例：

```json
{
  "command_id": "cmd_01J5RELOAD01",
  "task_id": "task_01J5PERSON01",
  "action": "RELOAD",
  "status": "SUCCEEDED",
  "requested_config_version": 5,
  "requested_at": "2026-08-14T06:30:00Z",
  "started_at": "2026-08-14T06:30:00.120Z",
  "completed_at": "2026-08-14T06:30:01.020Z",
  "result": {
    "runtime_state": "RUNNING",
    "applied_config_version": 5
  },
  "error": null
}
```

失败示例中的 `error`：

```json
{
  "code": "CONFIG_APPLY_FAILED",
  "message": "Detector 未能应用配置版本 5。",
  "retryable": true
}
```

前端提交命令后：

1. 禁用当前任务的互斥操作按钮。
2. 可每 1 秒轮询命令接口，或等待同一任务 WebSocket 的 `command_status` 消息。
3. 收到终态后重新获取任务详情，不能只在本地猜测最终状态。

命令保留期限暂定 7 天；过期后返回 `404 COMMAND_NOT_FOUND`。

## 11. WebSocket 实时接口

### 11.1 建立连接

```text
wss://vision.example.internal/api/v1/ws/detection-tasks/{task_id}
```

握手前 FastAPI 必须验证：

- 用户身份。
- `task_id` 是否存在。
- 用户是否有权查看任务。
- 当前用户和系统连接数限制。

连接成功后，一个 WebSocket 只订阅一个 DetectionTask。任务未启用也允许连接，以便页面接收 STOPPED 状态；没有最新检测帧时不伪造结果。

### 11.2 服务端消息

所有消息包含 `schema_version`、`type` 和 `sent_at_ms`。第一版支持以下类型：

#### connection_ready

```json
{
  "schema_version": 1,
  "type": "connection_ready",
  "task_id": "task_01J5PERSON01",
  "sent_at_ms": 1786689000000,
  "heartbeat_interval_ms": 15000
}
```

#### runtime_state

```json
{
  "schema_version": 1,
  "type": "runtime_state",
  "task_id": "task_01J5PERSON01",
  "sent_at_ms": 1786689000100,
  "enabled": true,
  "state": "RUNNING",
  "config_version": 5,
  "applied_config_version": 5,
  "last_heartbeat_at_ms": 1786689000050,
  "fps": 24.7,
  "inference_ms": 18.4,
  "error": null
}
```

#### frame_detection

```json
{
  "schema_version": 1,
  "type": "frame_detection",
  "task_id": "task_01J5PERSON01",
  "camera_id": "cam_01J5WASH01",
  "source_id": "src_01J5MAIN01",
  "algorithm_id": "region-person-detection",
  "algorithm_version": "2.1.0",
  "frame_id": 18272,
  "frame_ts_ms": 1786689000123,
  "published_at_ms": 1786689000180,
  "sent_at_ms": 1786689000185,
  "source_width": 1920,
  "source_height": 1080,
  "objects": [
    {
      "track_id": 12,
      "class_name": "person",
      "confidence": 0.96,
      "bbox": [0.21, 0.11, 0.48, 0.91],
      "attributes": {
        "helmet": false
      }
    }
  ],
  "metrics": {
    "inference_ms": 18.4,
    "fps": 24.7
  },
  "attributes": {}
}
```

`bbox` 固定为归一化 `[x1, y1, x2, y2]`，四项都在 `[0,1]`，且 `x1 < x2`、`y1 < y2`。

#### command_status

```json
{
  "schema_version": 1,
  "type": "command_status",
  "task_id": "task_01J5PERSON01",
  "sent_at_ms": 1786689001000,
  "command_id": "cmd_01J5RELOAD01",
  "action": "RELOAD",
  "status": "SUCCEEDED",
  "error": null
}
```

#### heartbeat

```json
{
  "schema_version": 1,
  "type": "heartbeat",
  "task_id": "task_01J5PERSON01",
  "sent_at_ms": 1786689015000
}
```

### 11.3 首帧、顺序和背压

连接建立后的推荐顺序：

1. 发送 `connection_ready`。
2. 发送最新 `runtime_state`。
3. 若 Redis 中 `vision:task:{task_id}:latest` 尚未过期，发送最近一条 `frame_detection`。
4. 持续转发 `vision:telemetry:{task_id}` 的新结果和状态/命令变化。

前端必须按 `frame_id` 去重并丢弃小于或等于最后已处理帧号的结果。Detector 重启导致帧号重新计数时，需要由后续协议增加 `stream_session_id`；第一版若观察到该场景，应把它提升为必需字段。

实时帧采用“最新覆盖旧帧”：

- 每个浏览器连接队列长度为 1 或很小。
- 客户端处理过慢时丢弃旧 `frame_detection`，不能无限积压。
- `runtime_state`、命令终态和错误状态不能被静默丢弃。

### 11.4 客户端消息与保活

第一版业务数据为服务端单向推送。客户端可以发送：

```json
{
  "type": "ping",
  "client_ts_ms": 1786689015000
}
```

服务端响应：

```json
{
  "schema_version": 1,
  "type": "pong",
  "client_ts_ms": 1786689015000,
  "sent_at_ms": 1786689015002
}
```

服务端 15 秒无业务消息时发送一次 `heartbeat`。前端连续两个心跳周期未收到任何消息时显示“实时数据连接中断”并指数退避重连。

### 11.5 关闭码

| 关闭码 | 含义 |
| --- | --- |
| `1000` | 正常关闭 |
| `1008` | 消息违反协议 |
| `1011` | 服务端内部或 Redis 订阅异常 |
| `4401` | 未认证 |
| `4403` | 无任务访问权限 |
| `4404` | 任务不存在 |
| `4429` | 连接数超限 |

FastAPI 中 WebSocket 依赖验证失败应使用 WebSocket 异常/关闭语义，不应在连接接受后再返回普通 HTTP JSON 错误。

## 12. 页面与接口映射

| 页面/操作 | 接口 |
| --- | --- |
| 侧边栏 Camera 数量 | `GET /cameras?page=1&page_size=1` 的 `total`，或随列表结果复用 |
| Cameras 卡片和搜索 | `GET /cameras?q=...` |
| Camera 卡片默认预览 | 列表取得默认 `source_id` 后调用 `GET /camera-sources/{source_id}/playback` |
| 添加 Camera | `POST /cameras` |
| Camera 详情 | `GET /cameras/{camera_id}` |
| 编辑 Camera/管理多路源 | `PUT /cameras/{camera_id}` |
| 详情切换默认源 | `PATCH /cameras/{camera_id}/default-preview-source` |
| 开始/停止页面预览 | 浏览器本地控制，无后端状态接口 |
| Detection Tasks 列表和搜索 | `GET /detection-tasks?q=...` |
| 创建任务的 Camera 选择器 | `GET /cameras` |
| 创建任务的源选择器 | `GET /cameras/{camera_id}/sources` |
| 算法选择器 | `GET /algorithms?status=ACTIVE` |
| 动态参数和 ROI 定义 | `GET /algorithms/{id}/versions/{version}` |
| 创建任务 | `POST /detection-tasks` |
| 任务详情 | `GET /detection-tasks/{task_id}` |
| 实时标注和运行状态 | `WS /ws/detection-tasks/{task_id}` |
| 任务视频 | 详情中的 `source_id` → `GET /camera-sources/{source_id}/playback` |
| 编辑任务 | `PUT /detection-tasks/{task_id}` |
| 启动/停止/重载/重启 | `POST /detection-tasks/{task_id}/commands` |
| 操作忙碌和最终结果 | `GET /detection-task-commands/{command_id}` 或 WebSocket `command_status` |
| 删除任务 | `DELETE /detection-tasks/{task_id}` |
| “显示 ROI”开关 | 前端本地页面偏好，本期不持久化、不调用 API |

为侧边栏数量单独请求完整列表开销较大。若未来页面并行加载或数据规模增大，可增加 `GET /api/v1/navigation-summary`；第一版不提前引入。

## 13. FastAPI/OpenAPI 落地约定

当前项目已经使用 `APIRouter(prefix="/api/v1")`。建议按业务边界拆分：

```text
backend/src/app/modules/
├── cameras/
│   ├── api/router.py
│   ├── schemas/camera.py
│   └── services/camera_service.py
├── algorithms/
│   ├── api/router.py
│   ├── schemas/algorithm.py
│   └── services/algorithm_catalog.py
├── detection_tasks/
│   ├── api/router.py
│   ├── schemas/task.py
│   ├── schemas/command.py
│   └── services/task_service.py
└── detection_runtime/
    ├── api/websocket.py
    ├── schemas/detection.py
    └── services/detection_hub.py
```

OpenAPI 要求：

- 每个路由设置稳定、唯一的 `operation_id`。
- 成功响应显式设置 `response_model` 和 `status_code`。
- `404/409/412/422/503` 使用 `responses` 声明统一 Problem 模型。
- 请求模型通过 Pydantic schema examples 提供与本文一致的示例。
- 枚举使用字符串 Enum/Literal，避免在 OpenAPI 中退化为无约束字符串。
- Algorithm 参数定义使用可辨识联合，以 `type` 作为 discriminator。
- REST 标签建议为 `health`、`cameras`、`algorithms`、`detection-tasks`、`detection-task-commands`。
- FastAPI 自动文档保留 `/docs` 和 `/openapi.json`；生产是否对外开放由部署策略决定。

FastAPI 422 默认格式应通过统一异常处理器转换为本文 Problem 模型，否则前端需要同时兼容两套字段错误协议。

WebSocket 不会像 REST 路由一样形成完整 OpenAPI 消息模型，因此应把第 11 节的消息联合模型同时维护为 Pydantic 模型，并在仓库文档或独立 AsyncAPI 文档中发布。

## 14. 数据与基础设施边界

### 14.1 PostgreSQL

保存：

- Camera、CameraSource。
- Algorithm 目录或从算法服务同步后的版本快照。
- DetectionTask Desired Config、`enabled`、`config_version`。
- 命令记录、幂等记录和可靠投递 outbox。

### 14.2 Redis

保存或传输：

- `vision:telemetry:{task_id}`：实时检测 Pub/Sub。
- `vision:task:{task_id}:latest`：最近一帧，建议 TTL 5 秒。
- `vision:task:{task_id}:runtime`：Actual State。
- `vision:worker:{worker_id}:heartbeat`：Detector 心跳，建议 TTL 10 秒。

Redis 不作为 Camera、任务或算法配置唯一事实源。Redis 暂时不可用时，REST 配置管理应尽量继续工作，运行状态返回 `UNKNOWN`。

### 14.3 MediaMTX

- FastAPI 封装其 Control API 与播放路径。
- 前端只得到业务化播放 URL，不直接调用 MediaMTX 管理 API。
- 视频流不进入 FastAPI、Redis 或 PostgreSQL。

### 14.4 Detector

- FastAPI 通过内部 gRPC 或等价控制通道执行命令。
- Detector 独立运行，FastAPI 重启不应停止已运行任务。
- Detector 通过 Redis 提供 Actual State 与实时检测元数据。

## 15. 待确认项对接口的影响

| PRD 问题 | 当前接口处理 | 确认后可能变化 |
| --- | --- | --- |
| Q-01 Camera 删除 | 本期不提供 | 增加 DELETE、引用和运行实例清理规则 |
| Q-02/Q-34 角色权限 | 预留 401/403 和安全方案 | 增加权限矩阵、审计字段 |
| Q-03 Algorithm 管理 | 只读目录 | 可能增加管理接口或改为外部服务代理 |
| Q-05 唯一性 | 仅同 Camera 源后缀去重 | 增加 DB 唯一索引和 409 错误 |
| Q-06 IP 类型 | 暂定 IPv4 | 字段可能演进为 `host` 或支持 IPv6/DNS |
| Q-07 保存前测试 | 创建/编辑不阻塞于连通性测试 | 可能增加连接测试接口或警告 |
| Q-08 源删除 | 被任务引用一律 409 | 若支持迁移，需要批量重绑接口 |
| Q-10 状态探测 | 返回状态、检查时间和错误 | 需冻结刷新、超时与状态枚举 |
| Q-12 凭据安全 | 按需求明文详情返回，标记安全例外 | 可能改为 secret replacement 语义 |
| Q-13/Q-17 算法 schema | 只冻结三种参数类型 | 扩展 discriminator 联合模型 |
| Q-14 离线源 | 允许保存、暂阻止启动 | 可能改为警告确认或强制启动 |
| Q-15 配置生效 | 保存只更新 Desired，显式 RELOAD | 可能改为自动下发 |
| Q-16 算法升级 | 任务固定具体版本 | 可能增加升级/回滚命令 |
| Q-18 无 ROI 算法 | 接口模型允许 `roi_definitions=[]`、`rois=[]` | 产品需确认空页面表现 |
| Q-19 ROI 背景 | 复用播放接口，由前端取当前画面 | 可能增加 snapshot 接口 |
| Q-20/Q-21 ROI | 归一化坐标和基础边界校验 | 增加旋转、裁剪和几何校验 |
| Q-22 显示 ROI | 本地偏好，不持久化 | 可能增加用户偏好接口 |
| Q-24 Actual State | 使用暂定枚举 | 枚举和转换表可能调整 |
| Q-25/Q-26 命令 | 202 + command resource + 幂等 | 超时、重试和互斥矩阵需冻结 |
| Q-27 运行中删除 | 暂禁止 | 可能变为“先停止再删除”的异步命令 |
| Q-28 版本/LKG | 暴露 Desired/Applied 版本 | LKG 和回退字段待增加 |
| Q-30/Q-31 结果协议 | 采用第 11 节 schema v1 | 字段、频率、延迟和重连目标待冻结 |

## 16. 联调与验收检查清单

### 16.1 Camera

- 缺少基础字段、没有源、多个默认源时返回字段级 `422`。
- 创建时服务端生成稳定 `camera_id/source_id`，去除 URL 后缀前导 `/`。
- 更新时保留已有源 ID，新源生成新 ID，删除被引用源返回 `409 SOURCE_IN_USE`。
- `If-Match` 过期返回 `412`，不会覆盖其他用户修改。
- 切换默认源不改变任务绑定。
- Camera 列表不返回凭据；详情按当前安全例外返回且设置 `no-store`。
- 停止浏览器预览不产生 Camera 或 Task 状态变更。

### 16.2 DetectionTask

- 创建时后端按 Algorithm schema 重新校验参数和全部 ROI。
- 新任务固定返回 `enabled=false`、`STOPPED`，不自动启动。
- 编辑任务不改变 `enabled` 或 Actual State，只增加配置版本。
- 停止任务不能 RELOAD/RESTART。
- 同一任务的互斥命令不会并发执行，重复请求通过 Idempotency-Key 去重。
- 运行中任务删除返回冲突；停止后删除返回 `204`。
- Redis 状态过期后不继续显示旧 RUNNING，而是 `UNKNOWN`。

### 16.3 Realtime

- WebSocket 连接前验证身份、任务存在性和权限。
- 建连后先发状态与未过期 latest，再转发新 Pub/Sub 数据。
- 消息中的 `task_id` 必须与 Redis channel 和 URL task_id 一致。
- Detector 消息先经过 Pydantic 校验，非法消息不推送并记录指标。
- 慢客户端只保留最新检测帧，不阻塞其他连接。
- 前端按 `frame_id` 去重，并用 `frame_ts_ms` 记录端到端延迟。
- Redis、FastAPI、浏览器分别断开后均能按设计恢复，Detector 推理不受 FastAPI 重启影响。

## 17. 评审结论要求

进入实现前至少需要对以下五项给出明确结论：

1. RTSP 凭据是否继续按需求明文返回，以及对应的访问控制边界。
2. Actual State 正式枚举、状态转换和 Redis 过期判定。
3. 离线源启动策略，以及运行中任务的删除策略。
4. 命令超时、失败回退、幂等保留期和配置保存后的生效策略。
5. 首批 Algorithm schema、ROI 坐标/几何规则和实时检测 schema v1。

未确认项应保持为显式设计暂定项，不得通过前端原型中的固定延时、数组下标或 `enabled` 状态映射替代生产后端语义。
