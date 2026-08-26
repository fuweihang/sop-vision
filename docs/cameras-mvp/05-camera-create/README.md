# 05｜创建 Camera

> 前置：[Foundation](../01-foundation/README.md)、[Stream Gateway Adapter](../03-stream-gateway-adapter/README.md)、[媒体对账](../04-media-reconciliation/README.md)
>
> 交付：`POST /api/v1/cameras`（`createCamera`）和新增表单

## 请求与响应

用户在一个表单中录入 Camera 连接信息和完整 Source 数组，指定唯一默认源，并以一个数据库事务
创建聚合。保存前不探测摄像头；合法的离线配置仍能成功。

```json
{
  "name": "洗手区 01",
  "ip_address": "192.168.1.64",
  "rtsp_port": 554,
  "username": "admin",
  "password": "camera-secret",
  "sources": [
    {
      "name": "主码流",
      "url_suffix": "Streaming/Channels/101",
      "is_default_preview": true
    },
    {
      "name": "子码流",
      "url_suffix": "/Streaming/Channels/102",
      "is_default_preview": false
    }
  ]
}
```

成功返回 `201 CameraDetail`、`Location: /api/v1/cameras/{camera_id}` 和
`Cache-Control: no-store`。CameraDetail 由[详情](../06-camera-detail/README.md)所有。创建 Source
不接受 `source_id`；公共字段规则见 [Foundation](../01-foundation/README.md#领域与字段)。

| 场景           | 字段 / code                                                   |
| -------------- | ------------------------------------------------------------- |
| 无 Source      | `sources/SOURCE_REQUIRED`                                     |
| 无默认源       | `sources/DEFAULT_SOURCE_REQUIRED`                             |
| 多个默认源     | 后续 `sources[i].is_default_preview/MULTIPLE_DEFAULT_SOURCES` |
| 规范化后缀重复 | 后续 `sources[i].url_suffix/DUPLICATE_SOURCE_SUFFIX`          |
| 只读或未知字段 | 对应字段 / `UNKNOWN_FIELD`                                    |

## 后端顺序

1. 验证并规范化请求，生成 Camera/Source UUID v4，按数组顺序构造聚合。
2. 在同一 UoW 中写入 Camera 与全部 Source 并提交；任意数据库失败完整回滚。
3. 提交成功后为全部新 Source 尽力调用 `ensure_path`，不得把 MediaMTX 调用放进数据库事务。
4. 共享一次完整 Path 快照计算 Source/Camera 状态；严格在线的 Source 才返回 `whep_url`。
5. MediaMTX 超时、不可用、无效响应或部分 Path 未就绪时仍返回 `201`，按状态契约降级；后台
   对账继续恢复映射。

数据库约束冲突转换为稳定字段错误，不公开 SQL 或约束名。数据库不可用返回
`503 DATABASE_UNAVAILABLE`；事务失败不得留下只有 Camera 或部分 Source 的数据。

## 前端规则

- 初始包含一路空 Source、默认选中，端口为 `554`；支持增删和排序。
- 新增 Source 不改变当前默认；删除默认源时选择剩余第一项；最后一路不可删除。
- 提交时禁止关闭和重复提交；失败保留输入，`422` 聚焦第一个错误字段。
- 结果未知的网络中断先刷新列表确认，不能自动重复写请求。
- 成功后失效 `cameras`；详情响应不进入浏览器持久化缓存。
- 创建响应有 `whep_url` 时可供后续播放器直接使用；为空时不由表单自动循环准备播放。

## 验收

- 单 Source、双 Source、十 Source 创建及固定 ID/时钟快照。
- 前导 `/` 被移除，顺序和唯一默认源正确，ID 均由服务端生成。
- 无 Source、多个默认源、重复后缀、非法 IPv4/端口得到准确字段错误。
- 数据库失败完整回滚；数据库提交后 MTX 失败仍返回 `201` 且下一轮对账可恢复。
- 在线 Path 返回 WHEP URL；离线、缺失或 Control API 故障返回确定状态和 `whep_url=null`。
- 表单成功、字段错误、数据库失败和未知提交结果均可独立演示；日志和错误没有测试密码。
