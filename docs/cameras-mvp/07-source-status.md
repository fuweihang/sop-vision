# 07｜CameraSource 状态

> 前置：[Cameras 基础契约](./01-foundation.md)  
> 交付：MediaMTX Control API Adapter、Path 状态映射、Camera 状态聚合及列表/详情投影

## 1. 完成目标

系统通过 MediaMTX Control API `/paths/list` 获取 Path 快照，将每路 CameraSource 映射为 `ONLINE/OFFLINE`，并在 Camera 列表和详情中返回确定的 Source 状态及 Camera 聚合状态。

状态不写入 PostgreSQL，也不使用进程内状态缓存。每次 Camera 列表或详情查询至多获取一次完整 Path 快照，再批量映射当前响应涉及的全部 Source。

## 2. 状态事实源

MediaMTX Control API 是 Source 状态的唯一事实源。后端调用：

```http
GET {mediamtx_control_api_base}/v3/paths/list
```

本文将该端点简称为 `/paths/list`。Control API 只允许 FastAPI 后端访问，Frontend 不得直接调用。

响应中的 Path 至少使用以下字段：

```json
{
  "items": [
    {
      "name": "8f14e45f-ea9d-4a7d-9b6d-8c9f0a1b2c3d",
      "available": true,
      "online": true
    }
  ]
}
```

- `available=true` 表示流当前可被读取。
- `online=true` 表示流由在线 Source 提供，而不是仅由离线内容提供。
- Adapter 必须按所使用的 MediaMTX OpenAPI 版本处理分页，直到获得完整 Path 列表。
- 任一分页请求失败或响应无法完整解析时，本次快照整体视为不可用，不得用部分页推导状态。
- Control API 请求总超时为 `500ms`；超时按请求失败处理。

## 3. Path 名称契约

每路 CameraSource 对应唯一 MediaMTX Path，Path `name` 直接等于 `source_id`：

```text
{source_id}
```

状态映射与播放模块必须复用同一个规则：`path_name = source_id.toString()`。不得添加任何前缀或后缀。后端以标准小写 UUID 文本执行大小写敏感的完整字符串比较。

Frontend 不得自行根据 `source_id` 拼接 MediaMTX URL。

## 4. Source 状态映射

Source 只允许两种状态：

| 状态 | 判定 |
| --- | --- |
| `ONLINE` | 找到 `name` 完全匹配的 Path，且 `available === true && online === true` |
| `OFFLINE` | 找不到匹配 Path，或 `available/online` 任一项不严格等于 `true` |

严格判定逻辑：

```text
matched_path = paths.find(path.name === expected_path_name)

ONLINE  = matched_path exists
          AND matched_path.available === true
          AND matched_path.online === true

OFFLINE = otherwise
```

不得对字符串 `"true"`、数字 `1` 或缺失字段执行 truthy 转换；它们都不严格等于布尔值 `true`，因此 Source 为 `OFFLINE`。

Source 状态摘要：

```json
{
  "source_id": "8f14e45f-ea9d-4a7d-9b6d-8c9f0a1b2c3d",
  "status": "ONLINE",
  "last_checked_at": "2026-08-19T03:00:00Z",
  "error": null
}
```

`last_checked_at` 是本次完整 `/paths/list` 快照成功或失败的完成时间。

## 5. OFFLINE 原因

`error` 仅在 `OFFLINE` 时返回稳定 code：

| code | 条件 |
| --- | --- |
| `MTX_PATH_NOT_FOUND` | 完整快照中找不到期望 `name` |
| `MTX_PATH_NOT_AVAILABLE` | Path 存在，但 `available` 不严格等于 `true` |
| `MTX_PATH_OFFLINE` | `available === true`，但 `online` 不严格等于 `true` |
| `MTX_CONTROL_API_UNAVAILABLE` | Control API 超时、网络失败或返回非成功状态 |
| `MTX_CONTROL_API_INVALID_RESPONSE` | JSON、分页或必需字段无法按固定 Schema 解析 |

当 `available` 和 `online` 同时不为 `true` 时，优先返回 `MTX_PATH_NOT_AVAILABLE`。

Control API 快照不可用时，当前响应涉及的全部 Source 均返回 `OFFLINE` 和相同的 Control API error code。Camera 配置查询仍返回 `200`，不得升级为列表或详情请求失败。

原始 MediaMTX 错误体不得直接进入业务 API。

## 6. Camera 聚合状态

Camera 至少包含一路 Source，聚合规则固定为：

1. 全部 Source 为 `ONLINE` → Camera `ONLINE`。
2. 全部 Source 为 `OFFLINE` → Camera `OFFLINE`。
3. 同时存在 `ONLINE` 和 `OFFLINE` → Camera `DEGRADED`。

`online_source_count` 只统计 `ONLINE`；`source_count` 来自 PostgreSQL 配置。

## 7. 范围

### 后端

- 类型化 MediaMTX Control API Client。
- `/paths/list` 完整分页读取、超时和响应校验。
- UUID Path 名称转换和 O(1) 名称索引。
- Source 状态映射及 Camera 聚合计算。
- 列表、详情和创建响应使用的批量投影端口。
- 依赖失败降级、指标和脱敏日志。

### 前端

- 列表和详情中的 `ONLINE/OFFLINE/DEGRADED` 状态徽标。
- 在线 Source 数和每路 Source 的 OFFLINE 原因。
- 页面可见时的低频 REST 刷新。

### 不属于本模块

- RTSP 直连探测或浏览器端状态推导。
- 状态历史、跨请求状态缓存、告警通知和 WebSocket 推送。
- 视频播放、录制或 MediaMTX 通用运维页面。

## 8. 后端端口

本模块不增加公共 REST 路由。它提供内部只读端口：

```text
fetch_path_snapshot() -> MediaPathSnapshot
project_source_statuses(source_ids[], snapshot) -> map[source_id, SourceStatusSummary]
aggregate_camera_status(source_statuses[]) -> CameraStatusSummary
```

端口规则：

- 同一个业务请求共享同一个不可变 Path 快照。
- Camera 列表的一页数据只调用一次 `/paths/list`，不得按 Camera 或 Source 分别请求。
- Camera 详情只调用一次 `/paths/list`。
- 创建响应可在数据库提交后调用一次 `/paths/list`；调用失败不回滚创建。
- 所有名称先建立 Map 索引，再映射 Source，避免每路 Source 线性扫描全部 Path。
- 重复 Path `name` 视为 `MTX_CONTROL_API_INVALID_RESPONSE`，不得任意选择其中一项。

## 9. 与配置和播放的关系

- 新建 Source 在 MediaMTX Path 出现且 `available/online` 都为 `true` 前展示 `OFFLINE`。
- Source 改名或排序不改变 Path 名称，也不改变状态映射。
- Camera 连接字段或 Source URL 后缀变化后，播放模块更新或重建同名 Path；在新 Path 同时 available 且 online 前展示 `OFFLINE`。
- Source 或 Camera 删除后，状态模块无需清理本地状态；播放模块尽力释放相应 Path。
- Source 为 `OFFLINE` 不阻止 Camera 配置保存或设为默认预览源。

## 10. 前端行为

- 列表和详情只展示 API 返回的状态，不自行请求 MediaMTX 或推导 Path 状态。
- 页面可见时每 15 秒后台刷新当前 Camera Query；页面隐藏时暂停轮询。
- 后台刷新保留现有配置内容，不显示整页加载状态。
- `ONLINE` 显示“在线”，`OFFLINE` 显示“离线”，Camera `DEGRADED` 显示“异常”。
- OFFLINE 原因只依据稳定 error code 显示，不展示 MediaMTX 原始错误。
- 刷新失败是 Camera API 自身失败；MediaMTX Control API 失败仍返回成功的 Camera 响应和 `OFFLINE` 状态。

## 11. 指标与日志

至少记录：

- `/paths/list` 成功、超时、非成功响应和无效响应数量。
- Control API 请求耗时和每次获得的 Path 数量。
- 本次投影的 `ONLINE/OFFLINE` Source 数和 `DEGRADED` Camera 数。
- Path 缺失、不可用和离线数量。
- 重复 Path name 和分页不完整数量。

日志允许包含 `camera_id/source_id/path_name/error_code/trace_id`，不得包含用户名、密码、完整 RTSP URL 或 MediaMTX 敏感响应体。

## 12. Fixture

必须提供 `MediaMtxControlApiStub`：

- 匹配 Path 且 `available=true/online=true`。
- Path `name` 直接使用 Source UUID。
- Path 不存在。
- `available=false/online=false`。
- `available=true/online=false`。
- `available/online` 缺失、类型错误或为非布尔值。
- 多页完整响应、某一页失败和重复 Path name。
- 超时、网络错误、非成功状态和无效 JSON。

前端提供三种 Camera 状态和全部 OFFLINE error code 的响应 Fixture。

## 13. 独立验收

1. 名称匹配且 `available === true && online === true` 时 Source 为 `ONLINE`。
2. Path `name` 与 `source_id` 的标准 UUID 文本完全相同，不含前缀或后缀。
3. Path 不存在、available 非 true 或 online 非 true 时 Source 为 `OFFLINE`。
4. 多 Source Camera 按全在线、全离线和混合状态正确聚合。
5. 一页 Camera 列表无论包含多少 Source 都只请求一次完整 Path 快照。
6. Control API 超时、失败或响应无效时 Camera 配置仍返回 `200`，Source 全部为 `OFFLINE`。
7. 分页不完整和重复 Path name 不会产生部分或随机状态。
8. Frontend 不直接访问 MediaMTX，也不出现未定义状态。
9. 日志和错误响应不泄露 RTSP 凭据或 MediaMTX 敏感内容。

## 14. MediaMTX 版本门禁

- 依赖版本必须固定，并从对应版本 OpenAPI 生成或校验 Control API Client。
- 契约测试只依赖 `name/available/online`，升级 MediaMTX 时必须先运行 Fixture 和集成测试。
- 若 `/paths/list` 路径、分页或字段类型发生变化，必须显式更新 Adapter；不得在运行时静默猜测字段。

## 15. Definition of Done

- Control API Client、分页、超时、Schema 校验和 Path 名称索引已实现。
- Source 二态映射、Camera 三态聚合和列表/详情投影已接入。
- Control API Stub 覆盖状态组合、分页和所有依赖故障。
- 前端三态展示、轮询和 OFFLINE 原因映射完成。
- 版本门禁、指标和脱敏日志已实现并记录。
