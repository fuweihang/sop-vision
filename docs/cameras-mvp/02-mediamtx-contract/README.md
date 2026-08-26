# 02｜MediaMTX 接口与部署契约

> 前置：[Foundation](../01-foundation/README.md)
>
> 交付：精确 MediaMTX 版本、受控 OpenAPI、网络/安全边界和 Stream Gateway Port；无新公共路由

本切片先消除所有外部协议猜测，再允许业务切片依赖 MediaMTX。它不实现 Camera handler 或浏览器
播放器，但必须用真实 MediaMTX 验证后续 Adapter 所需接口和字段。

## 版本与接口

- 镜像必须固定到精确版本或 digest；浮动的主版本标签不能作为受支持契约。
- 仓库保存与该版本一致、可审查的 MediaMTX OpenAPI 或生成 Client 输入；升级必须显式更新
  Fixture 和契约测试。
- Control API 只允许 Backend 和运维网络访问；Frontend 永不访问 `:9997`。
- 本 MVP 只依赖以下 v3 能力：

| 用途           | MediaMTX 接口                               |
| -------------- | ------------------------------------------- |
| 配置快照/单项  | `GET /v3/config/paths/list                  | get/{name}` |
| 幂等覆盖 Path  | `POST /v3/config/paths/replace/{name}`      |
| 删除 Path      | `DELETE /v3/config/paths/delete/{name}`     |
| 运行态完整快照 | `GET /v3/paths/list`                        |
| 浏览器读取     | `{PUBLIC_WEBRTC_BASE_URL}/{path_name}/whep` |

Control API 修改的是 MediaMTX 内存配置，不写回 `mediamtx.yml`。PostgreSQL 因而仍是 Desired
State 唯一事实源，重启恢复由[媒体对账](../04-media-reconciliation/README.md)负责。

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
fetch_path_snapshot()
ensure_path(desired_source)
release_path(source_id)
whep_url_for(source_id)
```

状态快照、播放准备和删除清理分别遵守 `500ms`、`3s` 和 `2s` 总等待上限；共享 HTTP Client 的
默认 timeout 不能覆盖用例级总预算。只有幂等且安全的读取/覆盖/删除允许有限重试，所有重试都
必须计入总预算。

MediaMTX 故障不能令 Backend 配置 API 整体失去就绪状态。进程/数据库 readiness 与媒体依赖健康
分开表达，媒体不可用通过投影、指标和日志降级。

## 安全与验收

- 使用真实锁定版本验证全部接口、方法、分页和响应字段。
- 证明 Control API 变更在 MediaMTX 重启后丢失，并由后续对账重建，而不是误以为已持久化。
- 覆盖 RTSP 用户名/密码包含 `@`、`:`、`%`、`#` 和空白时的组件编码。
- Backend 能访问 Control API，浏览器只能访问部署公开的 WHEP 地址。
- Control API 请求/响应、异常、访问日志和指标不包含密码或完整 RTSP URL。
- Codec、HTTPS、ICE 地址和局域网浏览器可达性进入[发布门禁](../11-release-gates/README.md)，不由
  Control API 连通性代替。
