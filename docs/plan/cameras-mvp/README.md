# Cameras MVP

> 当前状态：Foundation、MediaMTX 契约、Stream Gateway Adapter、媒体对账和创建已完成；06–11 尚未实现。
> REST 前缀：`/api/v1`。

本目录冻结 Cameras 第一阶段的产品边界、切片依赖和跨端契约。PostgreSQL 保存 Camera Desired
State；MediaMTX 保存可丢失的媒体 Runtime State。配置事务与媒体同步必须保持可区分：数据库
提交成功后，MediaMTX 失败只能令媒体投影降级，不能伪装成 Camera 创建、更新或删除回滚。

## 实现状态与顺序

| #   | 切片                                                          | 当前状态 | 公共 API 影响                                                  |
| --- | ------------------------------------------------------------- | -------- | -------------------------------------------------------------- |
| 01  | [Foundation](01-foundation/README.md)                         | 已完成   | 公共前置                                                       |
| 02  | [MediaMTX 契约](02-mediamtx-contract/README.md)               | 已完成   | 无新路由；已冻结外部协议与部署边界                             |
| 03  | [Stream Gateway Adapter](03-stream-gateway-adapter/README.md) | 已完成   | 无新路由；实现 Path 读写和状态投影                             |
| 04  | [媒体对账](04-media-reconciliation/README.md)                 | 已完成   | 无新路由；恢复 PostgreSQL → MediaMTX Desired State             |
| 05  | [创建](05-camera-create/README.md)                            | 已完成   | `POST /cameras`（`createCamera`）                              |
| 06  | [详情](06-camera-detail/README.md)                            | 未实现   | `GET /cameras/{camera_id}`（`getCamera`）                      |
| 07  | [播放准备](07-source-playback/README.md)                      | 未实现   | `POST /camera-sources/{source_id}/playback`                    |
| 08  | [列表](08-camera-list/README.md)                              | 未实现   | `GET /cameras`（`listCameras`）                                |
| 09  | [更新与默认源](09-camera-update-default-source/README.md)     | 未实现   | `PUT /cameras/{camera_id}`、`PATCH .../default-preview-source` |
| 10  | [删除](10-camera-delete/README.md)                            | 未实现   | `DELETE /cameras/{camera_id}`（`deleteCamera`）                |
| 11  | [发布门禁](11-release-gates/README.md)                        | 未实现   | 无新路由；端到端故障、安全和容量验收                           |

顺序表达的是完成依赖，不要求把同一切片的 Backend 与 Frontend 严格串行开发。02–04 已建立真实媒体
边界：04 提供共享 Desired State 构造和后台恢复，但不替 Camera handler 安装即时同步。05、09、10
在各自数据库提交后调用媒体 Port；11 只汇总跨切片发布门禁，不接收本应由前序切片完成的遗留实现。

## 产品范围

MVP 允许用户创建包含多路 RTSP Source 的 Camera，搜索和分页浏览列表，查看详情，完整编辑
Camera/Source 集合，切换默认预览源，查看运行状态，通过 WHEP 预览并删除 Camera。

```text
Camera 1 ─── N CameraSource
Camera.default_preview_source_id ─── 1 CameraSource

PostgreSQL CameraSource ── Desired State ──▶ MediaMTX Path
Browser ◀────────────── WHEP ─────────────── MediaMTX
```

本阶段不包含：

- 鉴权、RBAC、审计和多租户。
- Camera/Source 启停、厂商、批量管理和保存前连接测试。
- 录像、截图、回放和 WebSocket 状态推送。
- 软删除、恢复、跨业务引用保护和事务级 Outbox/Saga 媒体投递。

周期对账属于本 MVP：它用于恢复 MediaMTX 内存状态和清理受管孤儿 Path，但不把 Control API
操作提升为与 PostgreSQL 同一事务，也不承诺零窗口、恰好一次的外部副作用。

## 冻结决策

1. Camera 是聚合根，至少包含一路 Source，且恰好一路是默认预览源。
2. 持久化 ID 由服务端生成 UUID v4；MediaMTX Path 名称直接使用 Source ID 的小写标准文本。
3. PostgreSQL 是配置 Desired State 的唯一事实源；MediaMTX 配置和运行态都允许丢失并可重建。
4. Camera 创建、更新和删除先提交数据库，再尽力同步 MediaMTX；媒体失败不改变配置结果。
5. MVP 使用 `sourceOnDemand=false`，使 MediaMTX 持续连接 RTSP，`ONLINE/OFFLINE` 表达实际运行态。
6. 保存前不探测 RTSP；数据库成功不以 MediaMTX 或摄像头就绪为条件。
7. Source 为 `ONLINE/OFFLINE`，严格 Path 判定由 Adapter 切片所有；Camera 为
   `ONLINE/OFFLINE/DEGRADED`，由 Cameras Application 对同一批 Source 投影做纯聚合。
8. `listCameras` 和 `getCamera` 只观察一份状态快照，不创建 Path；严格在线时才返回非空
   `whep_url`。
9. Cards 和详情正常播放直接使用其响应中的 `whep_url`，不为每张 Card 先调用 FastAPI。
10. `prepareCameraSourcePlayback` 是幂等的按需准备/恢复命令，只在映射缺失或播放恢复时调用；它
    不能替代后台 Desired State 对账。
11. WHEP URL 由 FastAPI 按部署配置生成并返回；Frontend 不拼接 Path 或 MediaMTX 地址。
12. Camera 名称和 IPv4 不唯一；RTSP 端口默认 `554`，范围 `1–65535`。
13. 同 Camera 内规范化后的 `url_suffix` 大小写敏感唯一；更新保留已有 Source ID，缺失项即删除。
14. Camera 详情包含用户名、密码和完整 RTSP URL，必须 `Cache-Control: no-store` 并脱敏日志。
15. 列表按 `created_at ASC, camera_id ASC` 稳定分页；额外查询参数被忽略。
16. 删除只校验资源存在性；数据库提交后立即尽力释放 Path，后台对账继续清理遗留映射。
17. 预览启停只影响浏览器播放器，不改变 PostgreSQL 配置或删除 MediaMTX Path。
18. Backend 配置读写不能因 MediaMTX 故障整体失去服务；媒体依赖健康与 API 进程就绪分开表达。
19. Cameras MVP 使用脱敏结构化日志观察媒体链路，不单独引入指标框架、指标注册表或 `/metrics`
    路由。

字段、事务、HTTP、缓存和敏感数据公共规则见 [Foundation](01-foundation/README.md)。外部协议、
状态映射、恢复和播放器资源生命周期分别由 02、03、04、07 的唯一契约负责。

## MVP 完成标准

- 七个公共 Camera handler 均有真实 Application Service 与依赖装配，不再含占位异常。
- MediaMTX 使用精确版本和受测协议，Path 读写、状态快照、WHEP URL 与错误转换无运行时猜测。
- 创建、更新、删除的数据库后媒体同步和周期对账形成可恢复的 Desired/Runtime State 闭环。
- MTX 重启后由对账恢复全部当前 Source；Playback 只能作为用户按需自愈的第二道防线。
- 列表每页只获取一次 Path 快照；正常 Card 预览不产生逐 Card FastAPI 请求。
- OpenAPI、Frontend 类型、Client 和 Fixture 同源；Playback 只暴露具有准备/恢复语义的 `POST`。
- 凭据、完整 RTSP URL 和 MediaMTX 原始响应不越过 Foundation 定义的边界。
- 单元、PostgreSQL 集成、Adapter Fixture、真实 Adapter、Frontend、契约、敏感数据和端到端发布
  门禁全部通过。

发布前运行：

```bash
cd backend
uv run python scripts/check_camera_placeholders.py mvp
```

该命令在任一目标 handler 仍为占位时失败；完整发布命令和场景见
[发布门禁](11-release-gates/README.md)。
