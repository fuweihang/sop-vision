# 07｜CameraSource 状态

> 状态：目标契约已冻结，业务实现尚未开始。
>
> 前置：[Foundation](../01-foundation/README.md)
>
> 交付：MediaMTX `/paths/list` Adapter、Source 映射、Camera 聚合和前端状态展示；无新 REST 路由

## 事实源与快照

MediaMTX Control API `GET {base}/v3/paths/list` 是 Source 状态的唯一事实源。Frontend 不直接
访问它。Adapter 按锁定版本的 OpenAPI 读取全部分页；任一页失败、分页不完整、重复 Path 名称，
或 JSON/分页/Path `name` 无法解析时，整次快照不可用，不能用部分结果推导状态。

Control API 总超时为 `500ms`。同一个 Camera API 请求共享一份不可变快照：列表一页、详情或
创建响应各至多调用一次，并先建立 `name → Path` Map 后批量映射。

每路 Source 的 Path `name` 直接等于 `source_id` 的小写标准 UUID 文本，比较区分大小写且不
添加前后缀。Frontend 不自行拼接 Path 或 MediaMTX URL。

## 状态映射

```text
ONLINE = Path name 完全匹配
         AND available === true
         AND online === true
OFFLINE = 其他所有情况
```

`available/online` 的字符串 `"true"`、数字 `1`、缺失字段都不是布尔 `true`，按对应 Path
OFFLINE 处理，而不是令整份快照失效。`last_checked_at` 是本次完整快照成功或失败的完成时间。
OFFLINE 的稳定 `error` 为：

| code                               | 条件                                       |
| ---------------------------------- | ------------------------------------------ |
| `MTX_PATH_NOT_FOUND`               | 完整快照中没有匹配名称                     |
| `MTX_PATH_NOT_AVAILABLE`           | Path 存在但 available 不严格为 true        |
| `MTX_PATH_OFFLINE`                 | available 为 true，但 online 不严格为 true |
| `MTX_CONTROL_API_UNAVAILABLE`      | 超时、网络失败或非成功状态                 |
| `MTX_CONTROL_API_INVALID_RESPONSE` | JSON、分页、字段或名称唯一性无效           |

available 与 online 同时不为 true 时优先 `MTX_PATH_NOT_AVAILABLE`。快照不可用时，本次响应的
全部 Source 使用相同 Control API error；Camera 配置仍返回 `200`，原始媒体错误体不公开。

Camera 至少有一路 Source，聚合固定为：全在线 `ONLINE`、全离线 `OFFLINE`、混合
`DEGRADED`；`online_source_count` 只统计 ONLINE，`source_count` 来自 PostgreSQL。

## 与配置和播放的边界

- 新建 Source 在同名 Path 同时 available/online 前为 OFFLINE。
- Source 改名或排序不改变 Path；连接字段或后缀变化时由播放模块更新同名映射。
- Source/Camera 删除后状态模块不保存或清理本地状态；播放模块尽力释放 Path。
- OFFLINE 不阻止保存配置、选择默认源或尝试准备播放。
- `peek_playback` 只为已在线 Path 提供 `whep_url`，列表/详情读取不得主动创建映射。

内部端口保持职责单一：`fetch_path_snapshot()` 获取完整快照，
`project_source_statuses(source_ids, snapshot)` 批量映射，
`aggregate_camera_status(statuses)` 计算 Camera 聚合。它们不增加公共 REST 路由。

## 前端与可观测性

- 列表和详情只展示 API 状态；页面可见时每 15 秒后台刷新当前 Query，隐藏时暂停。
- 后台刷新保留配置内容；OFFLINE 原因按稳定 code 显示，不展示 MediaMTX 原始文本。
- UI 文案：Source `ONLINE/OFFLINE` 为“在线/离线”，Camera `DEGRADED` 为“异常”。
- 指标覆盖请求结果/耗时/Path 数、状态数量、各 OFFLINE 原因、重复名称和分页不完整。
- 日志只允许 ID、Path 名称、error code 和 trace ID，不包含凭据、RTSP URL 或敏感响应体。

## 验收

- Stub 覆盖严格布尔组合、Path 缺失、类型错误、多页、页失败、重复名称、超时、网络/HTTP
  错误和无效 JSON。
- 名称规则、二态映射、三态聚合及 OFFLINE 优先级准确。
- 任意数量 Source 的列表只获取一次完整快照；失败时配置仍 `200`。
- MediaMTX 版本升级必须先通过生成 Client 的契约和 Fixture 测试，字段变化不得运行时猜测。
