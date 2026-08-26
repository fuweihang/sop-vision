# 05｜更新 Camera 与 Source 集合

> 状态：目标契约已冻结，业务实现尚未开始。
>
> 前置：[Foundation](../01-foundation/README.md)、[详情](../04-camera-detail/README.md)
>
> 交付：`PUT /api/v1/cameras/{camera_id}`（`updateCamera`）和编辑表单

## 目标与请求语义

一次 PUT 完整替换 Camera 可变配置和 Source 集合。已有 Source 由稳定 `source_id` 识别；
无 ID 的项新增，请求中缺失的已有项删除，数组顺序成为新顺序，唯一
`is_default_preview=true` 项成为默认源。成功返回 `200 CameraDetail` 和 `no-store`。

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

在创建规则之外增加：

| 场景                 | 字段 / code                                       |
| -------------------- | ------------------------------------------------- |
| 非标准 Source UUID   | `sources[i].source_id/INVALID_UUID`               |
| Source 不属于 Camera | `sources[i].source_id/SOURCE_NOT_OWNED_BY_CAMERA` |
| 请求内重复 Source ID | 后续项 / `DUPLICATE_SOURCE_ID`                    |
| 只读字段             | 对应字段 / `UNKNOWN_FIELD`                        |

## 事务与媒体差异

后端锁定并读取最新聚合，验证完整请求，按 Source ID 计算保留/新增/删除/重排，在一个事务中
保存并提交。已有项保留 `source_id/created_at`；任意失败完整回滚。不存在返回
`404 CAMERA_NOT_FOUND`，字段错误返回 `422`，数据库不可用返回 `503`。

- Source 改名或排序不改变 Path 名称。
- Source 后缀变化时保留 ID，提交后尽力更新同名映射。
- Camera IP/端口/凭据变化时，提交后尽力更新全部所属映射。
- 删除 Source 后尽力释放映射；失败不回滚数据库，详情按状态规则降级。
- 服务端不比较版本；并发合法更新以最后完成提交者为准。

## 前端与验收

- 从最新 CameraDetail 初始化；已有行保存稳定 ID，新行只用 UI 临时 key。
- 删除最后一路禁用；删除默认源时选择剩余第一项；排序不改变 ID。
- 有未保存修改时离开需确认；提交失败保留输入和顺序。
- 成功后失效 `cameras`、当前 `camera` 和受删除/连接变化影响的 `playback`。
- 验收覆盖仅改名称、增删改排 Source、切换默认源、连接字段变化、错误所有权/重复项、事务
  回滚和媒体清理失败；日志与错误不得包含旧密码或新密码。
