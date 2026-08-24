# Cameras MVP

> 状态：实施基线；REST 前缀：`/api/v1`

本目录定义 Cameras 第一阶段的产品边界、公共契约和交付切片。文档职责如下：

| 事实                                   | 唯一所有者                                                      |
| -------------------------------------- | --------------------------------------------------------------- |
| MVP 范围、冻结决策、交付顺序           | 本文件                                                          |
| 领域、持久化、HTTP、安全和缓存公共规则 | [Foundation](./01-foundation/README.md)                         |
| 实施状态、步骤和验证命令               | [Foundation 执行计划](./01-foundation/execution-plan/README.md) |
| 精确 HTTP Schema                       | 步骤 6 生成的 `contracts/openapi.json`                          |
| 单个功能独有行为                       | 对应功能切片                                                    |

引用处只链接事实所有者，不复制全文。实际完成状态以代码和自动化测试为准。

## 范围

用户可以创建包含多路 RTSP Source 的 Camera，搜索和分页浏览列表，查看详情，完整编辑
Camera/Source 集合，切换默认预览源，查看运行状态，进行 WHEP 预览并删除 Camera。

本阶段不包含鉴权/RBAC/审计、跨业务删除保护、Camera 启停、厂商与批量管理、连接测试、
录像/截图/回放、WebSocket 状态推送及可靠异步媒体清理。

```text
Camera 1 ─── N CameraSource
Camera.default_preview_source_id ─── 1 CameraSource
```

配置以 PostgreSQL 为事实源；运行状态来自 MediaMTX `/paths/list`；播放会话只存在于浏览器。
FastAPI 返回 WHEP 地址但不代理视频字节。

## 交付顺序与 API

| #   | 切片                                            | 方法与路径                                          | `operation_id`            |
| --- | ----------------------------------------------- | --------------------------------------------------- | ------------------------- |
| 1   | [Foundation](./01-foundation/README.md)         | 公共前置                                            | —                         |
| 2   | [创建](./02-camera-create/README.md)            | `POST /cameras`                                     | `createCamera`            |
| 3   | [列表](./03-camera-list/README.md)              | `GET /cameras`                                      | `listCameras`             |
| 4   | [详情](./04-camera-detail/README.md)            | `GET /cameras/{camera_id}`                          | `getCamera`               |
| 5   | [更新](./05-camera-update/README.md)            | `PUT /cameras/{camera_id}`                          | `updateCamera`            |
| 6   | [默认源](./06-default-preview-source/README.md) | `PATCH /cameras/{camera_id}/default-preview-source` | `setDefaultPreviewSource` |
| 7   | [状态](./07-source-status/README.md)            | 无新路由                                            | —                         |
| 8   | [预览](./08-source-preview/README.md)           | `GET /camera-sources/{source_id}/playback`          | `getCameraSourcePlayback` |
| 9   | [删除](./09-camera-delete/README.md)            | `DELETE /cameras/{camera_id}`                       | `deleteCamera`            |

Foundation 内部严格顺序实施；Foundation 完成后，其余切片可依靠 Fixture/Fake 并行开发。

## 冻结决策

1. Camera 是聚合根，至少包含一路 Source，且恰好一路是默认预览源。
2. 持久化 ID 由服务端生成 UUID v4；API 只接受小写、带连字符的标准文本。
3. Camera 名称和 IPv4 不唯一；RTSP 端口默认 `554`，范围 `1-65535`。
4. 同 Camera 内规范化后的 `url_suffix` 大小写敏感唯一；更新保留已有 Source ID，缺失项即删除。
5. 保存不探测 RTSP；离线配置可以保存，也可以被设为默认源。
6. Source 为 `ONLINE/OFFLINE`；Camera 为 `ONLINE/OFFLINE/DEGRADED`。
7. MediaMTX Path 命名由状态契约统一定义，Frontend 不自行拼接。
8. Source 在线判定使用状态契约定义的严格布尔规则。
9. Camera 详情包含用户名、密码和完整 RTSP URL，必须 `Cache-Control: no-store` 并脱敏日志。
10. 列表不提供排序参数，使用 Foundation 定义的稳定顺序；额外参数被忽略。
11. 配置写入使用普通 HTTP 请求；服务端执行每个通过校验的请求，不实现版本比较或幂等键。
12. 删除只校验资源存在性；媒体映射在数据库提交后尽力释放，失败不改变配置结果。
13. 预览启停只影响浏览器播放器，不改变持久化配置。

状态判定、错误原因和超时由[状态切片](./07-source-status/README.md)所有；播放器和媒体错误由
[预览切片](./08-source-preview/README.md)所有。

## MVP 验收

- 创建、列表、详情、更新、默认源切换、状态、预览和删除形成完整闭环。
- 无 Source、重复后缀、错误默认源和非本 Camera Source 得到准确字段错误。
- MediaMTX 故障不阻止配置读取和写入；数据库事务失败不留下部分聚合。
- 页面区分首次加载、后台刷新、空数据、搜索无结果和可恢复失败。
- OpenAPI、前端类型与 Fixture 同源；发布代码中没有 Cameras 占位 handler。
- 后端和前端测试覆盖成功、校验、不存在、依赖故障和资源释放。
- 日志、错误、指标、浏览器持久化和非详情响应不包含密码或完整 RTSP URL。
