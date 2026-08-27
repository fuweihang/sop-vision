# 03｜Stream Gateway Adapter 与状态投影

> 状态：已完成
>
> 前置：[Foundation](../01-foundation/README.md)、[MediaMTX 契约](../02-mediamtx-contract/README.md)
>
> 当前边界：已实现 MediaMTX Path 读写、完整快照、Source 状态投影和 WHEP URL；没有新增公共路由

`app/modules/stream_gateway` 是 Backend 访问 MediaMTX 的唯一边界。它拥有外部协议适配和 Source
运行态投影，不拥有 Camera 配置、数据库事务、Camera 聚合或 HTTP Problem 转换。PostgreSQL 仍是
Desired State 的唯一事实源，MediaMTX 配置与运行态都可以丢失并由后续对账重建。

## 当前架构

```text
Settings
  → FastAPI lifespan 创建 MediaMTXAdapter
  → application.state.stream_gateway
  → StreamGatewayPort dependency

Application Service（后续切片）
  ├─ DesiredSource → ensure_path / release_path → MediaMTX Control API
  └─ fetch_runtime_path_snapshot → project_source_runtime → SourceRuntimeProjection
```

核心实现分工如下：

- `ports.py` 定义框架无关 Port、脱敏错误、Desired/Runtime 数据和投影不变量。
- `services/mediamtx.py` 实现 MediaMTX v1.20.1 的 HTTP、分页、预算、错误转换和 I/O 日志。
- `projection.py` 使用一次完整观察批量生成 Source 投影，不执行 I/O 或读取时钟。
- `urls.py` 负责发送给 MediaMTX 的 RTSP 组件编码和公开 WHEP URL 拼接。

`MediaMTXAdapter` 已由应用 lifespan 创建并关闭，FastAPI dependency 返回 `StreamGatewayPort` 而非
具体实现。当前 Camera handler 仍未消费该 dependency；04 负责共享 Desired State 构造和周期对账，
05–10 在各自请求用例中完成媒体调用与状态处理。

## Port 契约

| 能力                            | 当前语义                                                           |
| ------------------------------- | ------------------------------------------------------------------ |
| `fetch_runtime_path_snapshot()` | 读取全部 `/v3/paths/list` 分页，返回不可变运行态快照               |
| `fetch_config_path_snapshot()`  | 读取全部 `/v3/config/paths/list` 分页，返回对账所需配置快照        |
| `ensure_path(desired_source)`   | 使用 replace 语义令 UUID Path 收敛到调用方提供的最新 Desired State |
| `release_path(source_id)`       | 删除同名 Path；不存在的 `404` 按幂等成功处理                       |
| `whep_url_for(source_id)`       | 只拼接受控公开地址，不检查 Path 状态                               |

调用方必须从最新 PostgreSQL 数据构造 `DesiredSource`。Adapter 不缓存 Camera 凭据、不判断业务版本，也
不在调用内部重试。发送给 MediaMTX 的上游地址应由 `build_mediamtx_source_url()` 按 URI 组件编码，
不得使用包含用户名和密码的裸字符串拼接。

## 完整快照规则

运行态与配置快照共享以下完整性契约：

- 固定从 0-based 第 `0` 页开始，并使用 `itemsPerPage=100`。
- `itemCount/pageCount` 必须是非负严格整数，`bool` 不能冒充整数；`items` 必须是数组。
- 空集合只接受 `itemCount=0`、`pageCount=0` 和空 `items`。
- 第一页冻结总数和页数；后续页必须保持一致且不能提前为空，最终条目数必须等于 `itemCount`。
- 每项必须是 object，`name` 必须是非空且在整份快照内唯一的字符串。
- 任一页失败或无法证明完整性时整份快照失败，禁止向调用方返回部分 Path。

每次快照有覆盖全部分页的 `500ms` 总预算，超时会取消仍在进行的 HTTP 请求。
`MEDIAMTX_API_TIMEOUT` 只是共享 Client 的单次请求安全上限。成功快照的 `checked_at` 是全部分页
完成后的 UTC 时间。

## 完整运行态快照

`fetch_runtime_path_snapshot()` 只依赖锁定协议中的 `name`、`available` 和 `online`。额外字段被
忽略；`available/online` 只有原始 JSON 值严格为 `true` 时才转换为真，字符串、数字、`null` 或
缺失字段只令对应 Path 降级为离线，不会使整份快照失效。

一次 Camera 用例必须共享一份快照：先建立 `name → Path` Map，再批量投影全部 Source。调用方不得
逐 Source 请求 Control API，也不得在同一响应中混用多个观察时刻。

## 完整配置快照

`fetch_config_path_snapshot()` 为[媒体对账](../04-media-reconciliation/README.md)提供远端配置观察：

- 受管 Path 的所有权遵循 [MVP 冻结的 UUID Path 规则](../README.md#冻结决策)。其 `source` 或
  `sourceOnDemand` 缺失、类型错误时保留为未知值，由 Reconciler 判定为漂移并用数据库状态覆盖。
- 非受管 Path 只保留名称用于所有权隔离；其余字段不参与 Cameras 对账，也不能因字段异常阻塞
  受管 Path 恢复。
- 快照失败时 Reconciler 必须放弃整轮远端配置比较，不能基于部分结果删除或覆盖 Path。

## 严格状态映射

`project_source_runtime()` 接收有序且不重复的 Source UUID v4、完整快照或脱敏 Adapter 错误，返回
同序的不可变 `SourceRuntimeProjection` 元组：

| 观察结果                                      | 状态      | 稳定 error code                    |
| --------------------------------------------- | --------- | ---------------------------------- |
| 没有同名 Path                                 | `OFFLINE` | `MTX_PATH_NOT_FOUND`               |
| `available` 不严格为 `true`                   | `OFFLINE` | `MTX_PATH_NOT_AVAILABLE`           |
| `available=true`，但 `online` 不严格为 `true` | `OFFLINE` | `MTX_PATH_OFFLINE`                 |
| `available=true` 且 `online=true`             | `ONLINE`  | `null`                             |
| Control API 超时、网络失败或非成功状态        | `OFFLINE` | `MTX_CONTROL_API_UNAVAILABLE`      |
| 成功响应违反 JSON、分页或 Path 名称契约       | `OFFLINE` | `MTX_CONTROL_API_INVALID_RESPONSE` |

`available` 的优先级高于 `online`。两者都不为真时稳定返回 `MTX_PATH_NOT_AVAILABLE`。

投影数据自身强制以下不变量：

- Source ID 是标准 UUID v4，`last_checked_at` 是 UTC。
- `ONLINE` 必须同时满足 `error=null` 和非空 `whep_url`。
- `OFFLINE` 必须包含稳定 error code，并满足 `whep_url=null`。
- 成功投影使用快照的 `checked_at`；Adapter 失败时由调用方显式提供同一批次的失败完成时间。
- 只有严格在线的 Source 才调用 `whep_url_for()`；投影函数不读数据库、不再次请求 MediaMTX、不写
  日志，也不创建自己的 Clock。

`SourceRuntimeStatus` 和 `SourceRuntimeErrorCode` 定义在 Port 中，Cameras Pydantic Schema 直接复用
这两个枚举。Stream Gateway 因而不依赖 Cameras API Schema，OpenAPI 也不会维护另一套同值枚举。
Camera 的 `ONLINE/OFFLINE/DEGRADED` 聚合仍属于 Cameras Application。

## 故障、安全与可观测性

Port 只暴露两个不含原始请求上下文的错误类别：

- `StreamGatewayUnavailableError`：总预算超时、网络失败或非成功 HTTP 状态。
- `StreamGatewayInvalidResponseError`：HTTP 成功，但 JSON、分页或必需名称字段违反锁定契约。

异常和默认对象表示不得携带 Control API URL、响应正文、RTSP URL 或凭据。共享
`httpx.AsyncClient` 使用 `trust_env=False`，避免内部请求被环境代理意外转发。部署配置在应用启动
时校验：Control API 地址禁止凭据、query、fragment 和路径前缀；公开 WHEP 基础地址允许反向代理
路径前缀，但同样禁止凭据、query 和 fragment。

Adapter 只记录一次 I/O 的汇总日志，包括稳定 operation/outcome、耗时、Path 数、错误类别、Source
UUID 和 trace ID。快照不逐 Path 记录日志，纯投影函数不记录日志；Source 离线原因汇总留给消费
投影的 Cameras Application。

## 后续接入约束

- 04 使用配置快照实现启动和周期对账，并在轮次之间负责重试与退避。
- 05–10 通过 `StreamGatewayPort` 完成提交后媒体同步、请求级运行态投影和播放准备。
- Application Service 负责把 Port 错误转换为 API 降级或 HTTP Problem；Adapter 不依赖 FastAPI。
- MediaMTX 版本升级必须同步更新受控协议、Fixture 和真实容器门禁，不能在运行时猜测字段别名。

## 验证

单元测试覆盖分页完整性、严格布尔降级、500ms 总预算、无重试、配置所有权隔离、幂等写删、投影
不变量和敏感数据过滤。真实 Adapter 门禁使用锁定版本的独立临时容器，并保证清理测试容器：

```bash
cd backend
uv run python scripts/check_mediamtx_adapter.py
```
