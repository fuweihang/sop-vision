# 02｜创建 Camera

> 状态：目标契约已冻结，业务实现尚未开始。
>
> 前置：[Foundation](../01-foundation/README.md)
>
> 交付：`POST /api/v1/cameras`（`createCamera`）和新增表单

## 目标与契约

用户在一个表单中录入 Camera 连接信息和完整 Source 数组，指定唯一默认源，并以一个事务
创建聚合。保存不探测摄像头或 MediaMTX，合法的离线配置也能成功。

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
`Cache-Control: no-store`。CameraDetail 由[详情契约](../04-camera-detail/README.md)所有。

创建请求中的 Source 不接受 `source_id`；其他公共字段规则见
[Foundation 字段契约](../01-foundation/README.md#领域与字段)。聚合特有错误为：

| 场景           | 字段 / code                                                   |
| -------------- | ------------------------------------------------------------- |
| 无 Source      | `sources/SOURCE_REQUIRED`                                     |
| 无默认源       | `sources/DEFAULT_SOURCE_REQUIRED`                             |
| 多个默认源     | 后续 `sources[i].is_default_preview/MULTIPLE_DEFAULT_SOURCES` |
| 规范化后缀重复 | 后续 `sources[i].url_suffix/DUPLICATE_SOURCE_SUFFIX`          |
| 只读或未知字段 | 对应字段 / `UNKNOWN_FIELD`                                    |

## 行为

后端按以下顺序处理：验证并规范化；生成 Camera/Source UUID v4；按数组顺序构造 Source；在
同一 UoW 中保存并提交；提交后读取一次状态投影；返回详情。状态查询失败时按
[状态降级规则](../07-source-status/README.md)返回 `OFFLINE`，不得回滚已提交配置。

数据库约束冲突必须转换为稳定字段错误，不公开 SQL 或约束名。数据库不可用返回
`503 DATABASE_UNAVAILABLE`；事务失败不得留下只有 Camera 或部分 Source 的数据。

前端规则：

- 初始包含一路空 Source、默认选中，端口为 `554`；支持增删和排序。
- 新增 Source 不改变当前默认；删除默认源时选择剩余第一项；最后一路不可删除。
- 提交时禁止关闭和重复提交；失败保留输入，`422` 聚焦第一个错误字段。
- 结果未知的网络中断先刷新列表确认，不能自动重复写请求。
- 成功后失效 `cameras`；详情响应不进入浏览器持久化缓存。

## 验收

- 单 Source、双 Source、十 Source 创建及固定 ID/时钟快照。
- 前导 `/` 被移除，顺序和唯一默认源正确，ID 均由服务端生成。
- 无 Source、多个默认源、重复后缀、非法 IPv4/端口得到准确字段错误。
- 数据库失败完整回滚；状态服务失败不回滚；日志和错误中没有测试密码。
- 表单成功、字段错误、数据库失败和未知提交结果均可独立演示。
