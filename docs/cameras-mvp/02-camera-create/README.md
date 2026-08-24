# 02｜创建 Camera

> 前置：[Cameras 基础契约](../01-foundation/README.md)  
> 交付：`POST /cameras`、新增表单、聚合事务和独立验收场景

## 1. 完成目标

用户可以在一个表单中录入 Camera 基础信息和多路 CameraSource，指定唯一默认预览源，并以一个事务创建完整聚合。

保存不依赖摄像头在线或 MediaMTX；合法配置即使暂时离线也能成功创建。

## 2. 范围

### 后端

- 校验 Camera 基础字段和完整 Source 数组。
- 规范化 Source URL 后缀并检查重复。
- 生成稳定 `camera_id/source_id`。
- 在一个事务中保存 Camera、Source 和默认源。
- 返回 Camera 详情和 Location。

### 前端

- 提供新增 Camera 弹窗或页面表单。
- 支持动态增加、删除和排序 Source 行。
- 通过单选控件指定唯一默认预览源。
- 展示字段级错误并防止重复提交。
- 成功后关闭表单、刷新列表并进入明确的成功状态。

### 不属于本模块

- 保存前连接测试。
- Source 状态映射和实际视频播放。
- Camera 编辑或删除。

## 3. API

Foundation 已以 `operation_id=createCamera` 注册该路径。进入本切片时必须复用原 Router 和 DTO，
不得新建平行端点。

```http
POST /api/v1/cameras
Content-Type: application/json
```

请求：

```json
{
  "name": "洗手区 01",
  "ip_address": "192.168.1.64",
  "rtsp_port": 554,
  "username": "admin",
  "password": "camera-secret",
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

成功：

```http
HTTP/1.1 201 Created
Location: /api/v1/cameras/6f9619ff-8b86-4e4f-9f68-bb3f8f6f4f21
Cache-Control: no-store
```

```json
{
  "camera_id": "6f9619ff-8b86-4e4f-9f68-bb3f8f6f4f21",
  "name": "洗手区 01",
  "ip_address": "192.168.1.64",
  "rtsp_port": 554,
  "username": "admin",
  "password": "camera-secret",
  "default_preview_source_id": "8f14e45f-ea9d-4a7d-9b6d-8c9f0a1b2c3d",
  "status": "OFFLINE",
  "online_source_count": 0,
  "source_count": 2,
  "sources": [
    {
      "source_id": "8f14e45f-ea9d-4a7d-9b6d-8c9f0a1b2c3d",
      "name": "通道 1 主码流",
      "url_suffix": "Streaming/Channels/101",
      "rtsp_url": "rtsp://admin:camera-secret@192.168.1.64:554/Streaming/Channels/101",
      "is_default_preview": true,
      "status": "OFFLINE",
      "last_checked_at": "2026-08-19T03:00:00Z",
      "error": "MTX_PATH_NOT_FOUND",
      "whep_url": null
    },
    {
      "source_id": "3f2504e0-4f89-41d3-9a0c-0305e82c3301",
      "name": "通道 1 子码流",
      "url_suffix": "Streaming/Channels/102",
      "rtsp_url": "rtsp://admin:camera-secret@192.168.1.64:554/Streaming/Channels/102",
      "is_default_preview": false,
      "status": "OFFLINE",
      "last_checked_at": "2026-08-19T03:00:00Z",
      "error": "MTX_PATH_NOT_FOUND",
      "whep_url": null
    }
  ],
  "created_at": "2026-08-19T03:00:00Z",
  "updated_at": "2026-08-19T03:00:00Z"
}
```

新建提交后通过 MediaMTX `/paths/list` 投影状态。新 Path 尚不存在，或 `available/online` 任一项不为 `true` 时返回 `OFFLINE`；状态查询失败也不得回滚创建事务。

## 4. 字段校验

| 字段 | 规则 | `errors[].code` |
| --- | --- | --- |
| `name` | trim 后必填，最长 128 | `REQUIRED/STRING_TOO_LONG` |
| `ip_address` | 必填且为 IPv4 | `REQUIRED/INVALID_IP_ADDRESS` |
| `rtsp_port` | 整数 `1-65535` | `OUT_OF_RANGE` |
| `username` | 必填，最长 128 | `REQUIRED/STRING_TOO_LONG` |
| `password` | 必填，最长 512 | `REQUIRED/STRING_TOO_LONG` |
| `sources` | 至少一项 | `SOURCE_REQUIRED` |
| `sources[].name` | trim 后必填，最长 128 | `REQUIRED/STRING_TOO_LONG` |
| `sources[].url_suffix` | 规范化后必填，最长 1024 | `REQUIRED/STRING_TOO_LONG` |
| 默认源 | 恰好一个 `true` | `DEFAULT_SOURCE_REQUIRED/MULTIPLE_DEFAULT_SOURCES` |

同一请求中出现重复的规范化 `url_suffix` 时，错误放在第二个及后续重复项的 `sources[i].url_suffix`，code 为 `DUPLICATE_SOURCE_SUFFIX`。

创建请求中的 Source 不接受 `source_id`。如提供未知字段，后端返回 `422 VALIDATION_ERROR`，code 为 `UNKNOWN_FIELD`。

## 5. 后端处理流程

1. 验证并规范化请求。
2. 生成 Camera ID 和每个 Source ID。
3. 根据唯一 `is_default_preview=true` 项设置 `default_preview_source_id`。
4. 在同一事务写入 Camera，并按数组顺序写入 Source。
5. 提交后读取一次 MediaMTX `/paths/list` 并映射 Source 状态；请求失败时按 `OFFLINE` 返回。
6. 返回 `201`、Location 和 `Cache-Control: no-store`。

数据库唯一约束冲突必须映射回稳定的字段错误，不向客户端暴露 SQL 名称。

## 6. 前端表单行为

- 打开表单时 `rtsp_port` 默认为 `554`，初始包含一路空 Source 且默认选中。
- 新增 Source 后不自动改变当前默认源。
- 删除当前默认 Source 时，如果仍有其他 Source，前端选择删除后列表第一项作为新的默认源，并允许用户再次修改。
- 不允许删除最后一路 Source；按钮禁用并说明至少保留一路。
- URL 后缀可在失焦时展示规范化预览，但请求仍由后端最终规范化。
- 提交期间禁用关闭和再次提交按钮，按钮宽度保持稳定。
- 网络失败时保留当前表单，由用户重新确认后再次提交。
- `422` 错误滚动并聚焦到第一个错误字段。
- 成功后失效 `cameras` Query，不把包含密码的响应写入持久化浏览器缓存。

用户主动取消时直接丢弃未保存草稿；MVP 不提供草稿恢复。

## 7. 错误与恢复

| 场景 | 响应/行为 |
| --- | --- |
| 字段或聚合约束失败 | `422 VALIDATION_ERROR` |
| 数据库暂不可用 | `503 DATABASE_UNAVAILABLE`；表单保留输入 |
| 提交结果未知的网络断开 | 保留表单并刷新列表确认结果后再决定是否重新提交 |

任何失败都不得创建部分 Source 或只有 Camera 没有 Source 的数据。

## 8. Fixture

必须提供：

- 单 Source、双 Source 和十 Source 合法请求。
- 无 Source、多个默认源、重复后缀、非法 IP 和越界端口请求。
- 创建成功、字段错误和数据库不可用 Mock。
- 固定 ID/时钟，使响应快照稳定。

Source 状态和 `whep_url` 在本模块 Fixture 中固定为 `OFFLINE/null`。

## 9. 独立验收

1. 使用最小合法字段创建单 Source Camera。
2. 创建结果中的 `camera_id/source_id` 均为服务端生成的 UUID v4，且 Source 顺序与请求一致。
3. `/Streaming/Channels/102` 保存为 `Streaming/Channels/102`。
4. 重复后缀、无 Source 和多个默认源返回精确字段错误。
5. 数据库中断或事务回滚时不残留部分聚合。
6. 创建成功后列表缓存失效，用户得到明确成功反馈。
7. 日志、追踪和错误响应中找不到提交的测试密码。

## 10. Definition of Done

- 创建 API、领域服务和仓储事务已实现。
- `createCamera` 的占位 `NotImplementedError` 已由真实 Service 调用替换。
- 新增表单、动态 Source 行、默认源选择和错误映射已实现。
- OpenAPI、前端类型、后端测试、前端测试和端到端创建场景通过。
- 可在无真实摄像头、无状态服务和无 MediaMTX 时独立演示。
