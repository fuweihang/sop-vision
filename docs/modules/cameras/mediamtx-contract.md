# MediaMTX 接口与部署契约

> 相关文档：[Cameras 基础能力](foundation.md)

本文记录 Backend 当前支持的 MediaMTX 版本、受控 OpenAPI、网络和安全边界以及 Stream Gateway
Port。MediaMTX 协议必须通过真实实例验证，业务代码不得猜测外部字段。

## 版本与接口

- 镜像固定到精确版本 `1.20.1`；浮动的主版本标签不能作为受支持契约。
- 仓库保存与该版本一致、可审查的 MediaMTX OpenAPI 或生成 Client 输入；升级必须显式更新
  Fixture 和契约测试。
- Control API 只允许 Backend 和运维网络访问；Frontend 永不访问 `:9997`。
- 本 MVP 只依赖以下 v3 能力：

| 用途           | MediaMTX 接口                               |
| -------------- | ------------------------------------------- |
| 配置快照       | `GET /v3/config/paths/list`                 |
| 单项配置       | `GET /v3/config/paths/get/{name}`           |
| 幂等覆盖 Path  | `POST /v3/config/paths/replace/{name}`      |
| 删除 Path      | `DELETE /v3/config/paths/delete/{name}`     |
| 运行态完整快照 | `GET /v3/paths/list`                        |
| 浏览器读取     | `{PUBLIC_WEBRTC_BASE_URL}/{path_name}/whep` |

受控协议输入保存在 `contracts/mediamtx-openapi.json`，来源固定为 MediaMTX `v1.20.1` 官方
`api/openapi.yaml` 的最小子集。Compose 与 `.env.example` 使用同一精确 tag；升级必须同时审查
受控输入、真实协议测试和 Stream Gateway Adapter Fixture。

Control API 修改的是 MediaMTX 内存配置，不写回 `mediamtx.yml`。PostgreSQL 因而仍是 Desired
State 唯一事实源，重启恢复由[媒体对账](media-reconciliation.md)负责。

## Path 与上游配置

- Path 名称直接等于 Source ID 的小写标准 UUID v4 文本，不添加前后缀。
- Path 的 `source` 是当前 Camera 连接字段与 Source 后缀生成的 RTSP URL。
- 用户名、密码和后缀中的 URL 保留字符必须按 RTSP URI 组件正确编码；不能继续使用字符串裸拼接
  作为发给 MediaMTX 的上游地址。
- MVP 固定 `sourceOnDemand=false`。MediaMTX 在没有浏览器读者时仍连接 RTSP，使状态代表运行态而
  不是“最近是否有人播放”。
- WHEP URL 由 Backend 使用受校验的公开基础地址生成；Control API 不负责返回浏览器地址。
- MediaMTX 实例专用于 SOP Vision。只有符合标准 UUID v4 名称的 Path 由 Cameras 对账管理，避免
  删除运维手工配置的其他 Path。

## Port 与故障预算

应用层只依赖以下最小能力，不能接触 `httpx`、MediaMTX JSON 或原始错误体：

```text
fetch_runtime_path_snapshot()
fetch_config_path_snapshot()
ensure_path(desired_source)
release_path(source_id)
whep_url_for(source_id)
```

运行态和配置快照均由 Adapter 执行 `500ms` 总等待上限；共享 HTTP Client 的默认 timeout 只是
单次请求安全上限，不能覆盖外层预算。Adapter 不自动重试：播放准备的 `3s` 和删除全部 Path 的
`2s` 总预算分别由对应 Application Service 控制，周期恢复与退避由 Reconciler 跨轮处理。

`app/modules/stream_gateway/ports.py` 保存框架无关 Port 与最小数据形状；
`app/modules/stream_gateway/urls.py` 保存 RTSP 组件编码和 WHEP 地址规则。具体 `httpx`、分页聚合、
预算、错误转换、状态投影和 Adapter I/O 日志已由
[Stream Gateway](stream-gateway.md)实现；投影结果汇总日志仍由消费投影的 Cameras Application
负责。

MediaMTX 故障不能令 Backend 配置 API 整体失去就绪状态。由 `app/api/health.py` 提供的现有
`/api/v1/health/ready` 只检查 PostgreSQL；媒体不可用由 Stream Gateway 投影和消费投影的 Application
结构化日志降级表达，`stream_gateway` 不拥有也不新增公共健康路由。

## 安全与验收

- 使用真实锁定版本验证全部接口、方法、分页和响应字段。
- 证明 Control API 变更在 MediaMTX 重启后丢失；由 PostgreSQL 重建属于
  [媒体对账](media-reconciliation.md)验收。
- 覆盖 RTSP 用户名/密码包含 `@`、`:`、`%`、`#` 和空白时的组件编码。
- Backend 能访问 Control API，浏览器只能访问部署公开的 WHEP 地址。
- Control API 在线路上必须发送编码后的上游 RTSP URL；HTTP 调试日志、结构化日志、异常、追踪和
  错误上报不得记录请求/响应正文、凭据或完整 RTSP URL。
- Codec、HTTPS、ICE 地址和局域网浏览器可达性进入
  [发布门禁](../../plans/cameras-mvp/11-release-gates/README.md)，不由
  Control API 连通性代替。

真实协议门禁使用独立临时容器，不访问共享开发实例：

```bash
cd backend
uv run python scripts/check_mediamtx_contract.py
```
