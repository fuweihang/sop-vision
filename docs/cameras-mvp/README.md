# Cameras MVP

> 当前状态：Foundation 已完成；02–09 业务切片尚未实现。REST 前缀：`/api/v1`。

本目录冻结 Cameras 第一阶段的产品边界和跨端契约。`contracts/openapi.json` 已包含七个目标
operation，但 Backend handler 仍是纯占位；Frontend 只具备 Client、Mock 和页面骨架。

## 实现状态与契约

| #   | 切片                                          | 当前状态 | 方法与路径                                          | `operation_id`            |
| --- | --------------------------------------------- | -------- | --------------------------------------------------- | ------------------------- |
| 1   | [Foundation](01-foundation/README.md)         | 已完成   | 公共前置                                            | —                         |
| 2   | [创建](02-camera-create/README.md)            | 未实现   | `POST /cameras`                                     | `createCamera`            |
| 3   | [列表](03-camera-list/README.md)              | 未实现   | `GET /cameras`                                      | `listCameras`             |
| 4   | [详情](04-camera-detail/README.md)            | 未实现   | `GET /cameras/{camera_id}`                          | `getCamera`               |
| 5   | [更新](05-camera-update/README.md)            | 未实现   | `PUT /cameras/{camera_id}`                          | `updateCamera`            |
| 6   | [默认源](06-default-preview-source/README.md) | 未实现   | `PATCH /cameras/{camera_id}/default-preview-source` | `setDefaultPreviewSource` |
| 7   | [状态](07-source-status/README.md)            | 未实现   | 无新路由                                            | —                         |
| 8   | [预览](08-source-preview/README.md)           | 未实现   | `GET /camera-sources/{source_id}/playback`          | `getCameraSourcePlayback` |
| 9   | [删除](09-camera-delete/README.md)            | 未实现   | `DELETE /cameras/{camera_id}`                       | `deleteCamera`            |

Foundation 是 02–09 的共同前置。创建完成后列表和详情才能形成可用读路径；更新、默认源、
状态、预览和删除可在共享领域与持久化边界上继续实现。精确请求/响应 Schema 以生成的
`contracts/openapi.json` 为准，功能文档只描述业务语义。

## 产品范围

MVP 允许用户创建包含多路 RTSP Source 的 Camera，搜索和分页浏览列表，查看详情，完整编辑
Camera/Source 集合，切换默认预览源，查看运行状态，进行 WHEP 预览并删除 Camera。

```text
Camera 1 ─── N CameraSource
Camera.default_preview_source_id ─── 1 CameraSource
```

配置以 PostgreSQL 为事实源；Source 运行状态目标来自 MediaMTX Control API；播放会话只存在于
浏览器。FastAPI 返回 WHEP 地址但不代理视频字节。

本阶段不包含：

- 鉴权、RBAC、审计和多租户。
- Camera/Source 启停、厂商、批量管理和保存前连接测试。
- 录像、截图、回放和 WebSocket 状态推送。
- 软删除、恢复、跨业务引用保护和可靠异步媒体清理。

## 冻结决策

1. Camera 是聚合根，至少包含一路 Source，且恰好一路是默认预览源。
2. 持久化 ID 由服务端生成 UUID v4；API 只接受小写、带连字符的标准文本。
3. Camera 名称和 IPv4 不唯一；RTSP 端口默认 `554`，范围 `1–65535`。
4. 同 Camera 内规范化后的 `url_suffix` 大小写敏感唯一；更新保留已有 Source ID，缺失项即删除。
5. 保存不探测 RTSP；离线配置可以保存，也可以被设为默认源。
6. Source 为 `ONLINE/OFFLINE`；Camera 为 `ONLINE/OFFLINE/DEGRADED`。
7. MediaMTX Path 名称直接使用 Source ID；Frontend 不自行拼接 Path 或 WHEP URL。
8. Source 在线判定使用状态契约定义的严格布尔规则。
9. Camera 详情包含用户名、密码和完整 RTSP URL，必须 `Cache-Control: no-store` 并脱敏日志。
10. 列表不提供排序参数，按 `created_at ASC, camera_id ASC` 稳定分页；额外查询参数被忽略。
11. 服务端执行每个通过校验的写请求，不实现版本比较或幂等键。
12. 删除只校验资源存在性；媒体映射在数据库提交后尽力释放，失败不改变配置结果。
13. 预览启停只影响浏览器播放器，不改变持久化配置。

字段、事务、HTTP、缓存和敏感数据公共规则见
[Foundation](01-foundation/README.md)；MediaMTX 状态判定和播放器资源生命周期分别由
[状态](07-source-status/README.md)与[预览](08-source-preview/README.md)契约负责。

## MVP 完成标准

- 七个目标 handler 均有真实 Application Service 与依赖装配，不再含占位异常。
- 创建、列表、详情、更新、默认源、状态、预览和删除形成真实 Backend/UI 闭环。
- PostgreSQL 是配置事实源；媒体依赖失败按契约降级，不造成配置事务假回滚。
- OpenAPI、Frontend 类型和 Fixture 同源，生成物无漂移。
- 凭据与完整 RTSP URL 不越过 Foundation 定义的边界。
- 单元、PostgreSQL 集成、Frontend、契约和敏感数据门禁全部通过。

发布前运行：

```bash
cd backend
uv run python scripts/check_camera_placeholders.py mvp
```

该命令在任一目标 handler 仍为占位时失败。
