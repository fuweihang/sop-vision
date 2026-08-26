# 03｜Stream Gateway Adapter 与状态投影

> 前置：[Foundation](../01-foundation/README.md)、[MediaMTX 契约](../02-mediamtx-contract/README.md)
>
> 交付：MediaMTX Path 读写 Adapter、批量状态投影和 WHEP URL 生成；无新公共路由

`app/modules/stream_gateway` 拥有 MediaMTX 运行时能力，不拥有 Camera 配置。Adapter 接收已经由
Application Service 组装的 Desired Source，只负责协议转换、超时、错误分类和敏感数据过滤。

## 完整运行态快照

`fetch_path_snapshot()` 调用锁定版本的 `GET /v3/paths/list` 并读取全部分页。任一页失败、分页
不完整、重复 Path 名称，或 JSON、分页字段、Path `name` 无法解析时，整次快照不可用；不能用
部分结果推导部分 Camera 在线。

Control API 总等待上限为 `500ms`。同一个 Camera API 请求共享一份不可变快照：列表一页、详情
或创建响应各至多调用一次，并先建立 `name → Path` Map 后批量映射。

## 严格状态映射

```text
ONLINE = Path name 完全匹配
         AND available === true
         AND online === true
OFFLINE = 其他所有情况
```

`available/online` 的字符串 `"true"`、数字 `1` 或缺失字段都不是布尔 `true`。类型不匹配只令
对应 Path 离线；快照结构、分页或名称集合无法可信解析时才令整份快照无效。

| 稳定 error code                    | 条件                                       |
| ---------------------------------- | ------------------------------------------ |
| `MTX_PATH_NOT_FOUND`               | 完整快照中没有匹配名称                     |
| `MTX_PATH_NOT_AVAILABLE`           | Path 存在但 available 不严格为 true        |
| `MTX_PATH_OFFLINE`                 | available 为 true，但 online 不严格为 true |
| `MTX_CONTROL_API_UNAVAILABLE`      | 超时、网络失败或非成功状态                 |
| `MTX_CONTROL_API_INVALID_RESPONSE` | JSON、分页、字段或名称唯一性无效           |

available 与 online 同时不为 true 时优先 `MTX_PATH_NOT_AVAILABLE`。`last_checked_at` 是完整快照
成功或失败的完成时间。快照不可用时，本次响应的全部 Source 使用相同 Control API error；原始
MediaMTX 错误体不公开。

Camera 聚合固定为：全在线 `ONLINE`、全离线 `OFFLINE`、混合 `DEGRADED`；
`online_source_count` 只统计 ONLINE，`source_count` 来自 PostgreSQL。

## Path 写入和释放

- `ensure_path(desired_source)` 使用 replace 语义把同一 Source ID 收敛到同一 Path 配置；重复调用
  不创建第二个 Path。
- `desired_source` 只包含 Adapter 必需的 Path 名称、已编码上游 URL 和固定媒体选项；不得进入
  默认日志或异常字符串。
- `release_path(source_id)` 删除同名配置；已不存在按幂等成功处理。
- 并发覆盖收到的 Desired State 必须来自调用方最新数据库读取；Adapter 不缓存 Camera 凭据或
  自行判断业务版本。
- `whep_url_for(source_id)` 只做受控基础地址与标准 UUID Path 拼接，不检查媒体状态。
- 投影层只在 Path 严格在线时公开 `whep_url`；缺失、离线或快照失败一律返回 `null`。

## 测试与可观测性

- 协议 Fixture 覆盖严格布尔组合、多页、页失败、重复名称、超时、网络/HTTP 错误和无效 JSON。
- 写 Adapter 覆盖新增、重复覆盖、配置变化、删除、重复删除和 MediaMTX 无效响应。
- 指标覆盖请求结果/耗时/Path 数、状态数量、各 OFFLINE 原因、重复名称和分页不完整。
- 日志只允许 Source ID、Path 名称、稳定 error code 和 trace ID，不包含凭据、RTSP URL 或原始
  MediaMTX 敏感响应。
- MediaMTX 版本升级必须先通过生成 Client 或协议 Fixture 契约，字段变化不得运行时猜测兼容。
