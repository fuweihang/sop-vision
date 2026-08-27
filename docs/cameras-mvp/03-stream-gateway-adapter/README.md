# 03｜Stream Gateway Adapter 与状态投影

> 前置：[Foundation](../01-foundation/README.md)、[MediaMTX 契约](../02-mediamtx-contract/README.md)
>
> 交付：MediaMTX Path 读写 Adapter、批量状态投影和 WHEP URL 生成；无新公共路由

`app/modules/stream_gateway` 拥有 MediaMTX 运行时能力，不拥有 Camera 配置。Adapter 接收已经由
Application Service 组装的 Desired Source，只负责协议转换、超时、错误分类和敏感数据过滤。
协议适配与状态投影保持分离：Adapter 返回框架无关快照，纯函数批量生成 Source 投影，不建立
有状态投影 Service，也不让 Stream Gateway 负责 Camera 聚合。

## 分页完整性

运行态和配置快照固定使用 `itemsPerPage=100`，始终先请求 0-based 的第 `0` 页取得计数。顶层必须
是 JSON object；每页的 `itemCount/pageCount` 必须是非负严格整数，`bool` 不能冒充整数，`items`
必须是数组。`itemCount=0` 时只接受 `pageCount=0` 和空 `items`；非空快照继续读取到
`pageCount - 1`，且要求 `pageCount >= 1`。`pageCount` 声明的每一页都必须非空；最后一页可以少于
`itemsPerPage`，其他页也不依赖“恰好 100 条”的额外假设。第一页冻结计数，后续每页必须保持
一致，最终收集条数必须等于 `itemCount`。

每个 Path 的 `name` 必须是非空字符串，整份快照内不得重复。读取期间发生页数或计数变化、提前
空页、最终条数不一致或名称无法可信解析时，整份快照无效。未知额外字段可以忽略；异常页数由
快照 `500ms` 总预算终止，不增加新的分页上限配置。

## 完整运行态快照

`fetch_runtime_path_snapshot()` 调用锁定版本的 `GET /v3/paths/list` 并读取全部分页。任一页失败、
分页不完整或结构字段无法解析时，整次快照不可用；不能用部分结果推导部分 Camera 在线，也不能
猜测字段别名或兼容其他版本。

同一个 Camera API 请求共享一份不可变快照：列表一页、详情或创建响应各至多调用一次，并先建立
`name → Path` Map 后批量映射。

## 完整配置快照

`fetch_config_path_snapshot()` 调用 `GET /v3/config/paths/list` 并读取全部分页。JSON、分页字段、
Path `name` 和名称唯一性遵守上述整份有效性规则；失败时不能把部分配置交给对账。

- 对符合小写标准 UUID v4 的受管 Path，`source` 必须是字符串且 `sourceOnDemand` 必须是严格布尔
  值。字段缺失或类型错误不伪装成合法配置，而是在快照中保留为未知值，由 04 将该 Path 判定为
  漂移并使用 PostgreSQL Desired State 覆盖。
- 对非受管 Path，只可靠读取名称用于所有权隔离；其余配置不参与 Cameras 对账，也不因无关字段
  缺失而令受管 Path 无法恢复。
- 配置快照同样不可变，`checked_at` 使用全部分页读取成功后的 UTC 完成时间。

## 最小错误分类

Port 增加两个框架无关、可由后续 Application Service 稳定区分的脱敏错误类别：

| 错误类别                            | 条件                                          |
| ----------------------------------- | --------------------------------------------- |
| `StreamGatewayUnavailableError`     | 超时、网络失败或非成功 HTTP 状态              |
| `StreamGatewayInvalidResponseError` | 成功响应的 JSON、分页或必需字段违反锁定的契约 |

这里的必需字段只包括分页结构和每个 Path 的 `name`。运行态 `available/online` 和受管配置
`source/sourceOnDemand` 使用下文定义的单 Path 降级规则，不把整份快照误判为无效。

错误不携带请求 URL、MediaMTX 原始响应体、上游 RTSP URL 或凭据。`release_path()` 收到 Path 不存在的
`404` 按幂等成功处理。HTTP Problem 的 `502/503` 转换属于后续 Cameras Application/API，不进入
Stream Gateway Port。

## 超时与重试边界

`fetch_runtime_path_snapshot()` 和 `fetch_config_path_snapshot()` 各自遵守 `500ms` 总预算；预算
覆盖全部分页并在到期时取消仍在进行的 HTTP 请求。`MEDIAMTX_API_TIMEOUT` 只作为共享 Client 的
单次请求安全上限。

Adapter 不自动重试读取、覆盖或删除。Playback 的 `3s` 和删除全部 Path 的 `2s` 属于后续
Application Service 总预算；Reconciler 在轮次之间退避和重试。这样 03 不建立与业务用例、周期
恢复相互叠加的第二套重试机制。

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
| `MTX_CONTROL_API_INVALID_RESPONSE` | JSON、分页、结构字段或名称唯一性无效       |

available 与 online 同时不为 true 时优先 `MTX_PATH_NOT_AVAILABLE`。`last_checked_at` 是完整快照
成功或失败的完成时间。快照不可用时，本次响应的全部 Source 使用相同 Control API error；原始
MediaMTX 错误体不公开。

投影层在 Stream Gateway Port 定义框架无关的 `SourceRuntimeStatus`、
`SourceRuntimeErrorCode` 和不可变 `SourceRuntimeProjection`。Cameras API Schema 直接复用前两个
`StrEnum`，不重复维护同值字符串；Stream Gateway 不依赖 Pydantic Camera Schema。

`SourceRuntimeProjection` 包含 Source ID、状态、`last_checked_at`、稳定 error code 和可空 WHEP
URL，并保持以下不变量：

- Source ID 必须是标准 UUID v4；所有完成时间必须是带时区 UTC。
- `ONLINE` 必须同时满足 `error=null` 和非空 `whep_url`。
- `OFFLINE` 必须包含一个稳定 error code，且 `whep_url=null`。

批量投影使用一个纯函数：输入有序且不重复的 Source ID 序列、不可变快照或上述两个 Adapter 错误
类别、失败时显式提供的完成时间以及 `whep_url_for` callable，返回与输入同序的不可变投影元组。
重复 Source ID 或不满足上述互斥组合的参数属于调用方错误并立即拒绝。成功使用快照自身的
`checked_at`，不得另造观察时间；失败时间由调用方使用项目现有 Clock 生成并显式传入。函数只在
Source 严格在线时调用 `whep_url_for`，不读取 PostgreSQL、不发起第二次 Control API 请求、不写
日志，也不创建自己的 Clock 抽象。

Camera 聚合留在 Cameras Application，并遵循
[MVP 冻结决策](../README.md#冻结决策)；API 响应组装只消费框架无关 Source 投影。共享 Camera 聚合
函数及其状态组合测试从 05 开始由 Cameras Application 切片负责，不进入 03。

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

## 配置与依赖装配

单个 `MediaMTXAdapter` 实现完整 `StreamGatewayPort`，内部持有 lifespan 级共享
`httpx.AsyncClient`，构造时接收 `MEDIAMTX_API_URL`、`MEDIAMTX_API_TIMEOUT` 和
`PUBLIC_WEBRTC_BASE_URL`。应用退出时关闭 Adapter，`application.state` 保存 Port，FastAPI
dependency 返回 Port 而不是具体 Client；测试可直接注入 Fake Port，不增加通用依赖容器或
Adapter Factory。

配置在应用启动时验证：Control API 地址必须是无凭据、query、fragment 和路径前缀的绝对
HTTP(S) URL，仅允许尾 `/`；WHEP 基础地址必须是无凭据、query 和 fragment 的绝对 HTTP(S) URL，
但允许反向代理路径前缀。格式错误属于部署配置错误并令应用启动失败；只有运行期间依赖不可用才
进入媒体状态降级。

## 测试与可观测性

- 协议 Fixture 覆盖运行态与配置快照的 0-based 多页、计数变化、提前空页、重复/空名称、超时、
  网络/HTTP 错误和无效 JSON；配置快照额外覆盖受管字段未知以及非受管 Path 隔离。
- 纯投影测试覆盖严格布尔组合、错误优先级、成功/失败检查时间、UTC 时间约束、批量同一观察时刻、
  输入顺序、重复 ID 和投影字段不变量；测试直接传入固定时间，不新增投影时钟实现。
- Adapter 测试覆盖新增、重复覆盖、配置变化、删除、重复删除、MediaMTX 无效响应、`500ms` 总预算
  和不自动重试。
- 03 只记录 Adapter I/O 汇总：稳定 `operation/outcome`、耗时、Path 数和 Adapter 错误类别；单
  Path 写入/释放可以记录 Source ID，禁止为快照逐 Path 输出日志。Source 离线数和按稳定 error
  code 汇总的 OFFLINE 原因由后续消费投影的 Cameras Application Service 记录，纯投影函数不写
  日志。
- MVP 不引入 `structlog`、JSON Formatter 或全局日志重构。Adapter 使用标准 `logging`，在默认
  控制台可见的稳定 `key=value` 消息中输出已批准字段，同时通过 `extra` 保存同值字段供测试；
  trace ID 直接读取现有请求上下文，非 HTTP 后台任务固定输出 `trace_id=-`，不依赖尚未装配到生产
  Handler 的 Filter。
- 日志中的资源标识只允许 Source ID 或等值的 UUID Path 名称；其他字段必须是上述低基数结果、计数、
  耗时、稳定 error code 和 trace ID，不包含凭据、RTSP URL 或 MediaMTX 原始敏感响应。
- MediaMTX 版本升级必须先通过生成 Client 或协议 Fixture 契约，字段变化不得运行时猜测兼容。

真实 Adapter 门禁使用锁定版本的独立临时容器，覆盖 Path 新增/覆盖、配置与运行态快照、删除与
重复删除、WHEP 路径前缀，并始终清理容器；多页故障仍由 Fixture 精确验证：

```bash
cd backend
uv run python scripts/check_mediamtx_adapter.py
```
