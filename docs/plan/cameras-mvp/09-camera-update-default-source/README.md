# 09｜更新 Camera 与切换默认源

> 前置：[详情](../06-camera-detail/README.md)、[媒体对账](../04-media-reconciliation/README.md)、[Playback](../07-source-playback/README.md)
>
> 交付：`PUT /api/v1/cameras/{camera_id}`、`PATCH /api/v1/cameras/{camera_id}/default-preview-source` 和对应详情交互

## 完整更新 Camera

PUT 完整替换 Camera 可变配置和 Source 集合。已有 Source 由稳定 `source_id` 识别；无 ID 的项
新增，请求中缺失的已有项删除，数组顺序成为新顺序，唯一 `is_default_preview=true` 项成为
默认源。成功返回 `200 CameraDetail` 和 `Cache-Control: no-store`。

```json
{
  "name": "洗手区东侧 01",
  "ip_address": "192.168.1.65",
  "rtsp_port": 554,
  "username": "admin",
  "password": "new-camera-secret",
  "sources": [
    {
      "source_id": "3f2504e0-4f89-41d3-9a0c-0305e82c3301",
      "name": "子码流",
      "url_suffix": "Streaming/Channels/102",
      "is_default_preview": true
    },
    {
      "name": "通道 2",
      "url_suffix": "Streaming/Channels/201",
      "is_default_preview": false
    }
  ]
}
```

| 场景                 | 字段 / code                                       |
| -------------------- | ------------------------------------------------- |
| 非标准 Source UUID   | `sources[i].source_id/INVALID_UUID`               |
| Source 不属于 Camera | `sources[i].source_id/SOURCE_NOT_OWNED_BY_CAMERA` |
| 请求内重复 Source ID | 后续项 / `DUPLICATE_SOURCE_ID`                    |
| 只读字段             | 对应字段 / `UNKNOWN_FIELD`                        |

后端锁定并读取最新聚合，验证请求，计算保留/新增/删除/重排，在一个事务中保存并提交。已有项保留
`source_id/created_at`；任意数据库失败完整回滚。不存在返回 `404 CAMERA_NOT_FOUND`，字段错误
返回 `422`，数据库不可用返回 `503`。

数据库提交后按 diff 执行媒体同步：

- Source 只改名称或排序不改变 Path，也不重载媒体连接。
- 新增 Source 调用 `ensure_path`；后缀变化时保留 ID 并覆盖同名 Path。
- Camera IP、端口或凭据变化时，确保全部所属 Path 使用新 Desired State。
- 删除 Source 后立即尽力 `release_path`；失败不回滚，后台对账继续清理。
- 同步后共享一次状态快照生成 CameraDetail；媒体故障不改变 `200` 配置结果。

服务端不比较前端版本；并发合法更新以数据库最后完成提交者为准，媒体最终由对账收敛到数据库
最新状态。

## 切换默认预览源

```json
{ "source_id": "3f2504e0-4f89-41d3-9a0c-0305e82c3301" }
```

成功返回：

```json
{
  "camera_id": "6f9619ff-8b86-4e4f-9f68-bb3f8f6f4f21",
  "default_preview_source_id": "3f2504e0-4f89-41d3-9a0c-0305e82c3301",
  "updated_at": "2026-08-19T03:10:00Z"
}
```

后端锁定 Camera，确认 Source 属于该聚合，原子更新默认 ID 和 `updated_at`。离线 Source 也可以
设为默认。切换不修改 Source 配置、顺序或 MediaMTX Path；当前浏览器播放器由 Frontend 正常
关闭，再由新默认 Source 的最新列表/详情投影决定是否直接播放或恢复。

Camera 不存在返回 `404 CAMERA_NOT_FOUND`；Source 不存在或不属于 Camera 返回
`source_id/SOURCE_NOT_OWNED_BY_CAMERA`；数据库不可用返回 `503 DATABASE_UNAVAILABLE`。

## 前端与验收

- 编辑表单从最新 CameraDetail 初始化；已有行保存 ID，新行只使用 UI 临时 key。
- 删除最后一路禁用；删除默认源时选择剩余第一项；排序不改变 Source ID。
- 有未保存修改时离开需确认；提交失败保留输入和顺序。
- 默认源提交期间禁用全部单选项；失败恢复原状态，不保留错误的乐观结果。
- 更新成功后失效 `cameras`、当前 `camera` 和受连接变化/删除影响的 `playback` 内存数据。
- 默认源切换成功后失效 `cameras` 和当前 `camera`，并关闭旧默认源播放器。
- 验收覆盖增删改排、连接字段变化、配置 diff、Path 同步失败及对账恢复、默认源在线/离线、
  所有权错误、事务回滚、并发更新和新旧密码脱敏。
