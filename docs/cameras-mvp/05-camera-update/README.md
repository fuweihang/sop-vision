# 05｜更新 Camera 与 Source 集合

> 前置：[Cameras 基础契约](../01-foundation/README.md)、[Camera 详情](../04-camera-detail/README.md)  
> 交付：`PUT /cameras/{camera_id}`、编辑表单和 Source 差异保存

## 1. 完成目标

用户可以编辑 Camera 基础字段，并在同一次保存中增加、修改、排序或删除 CameraSource。保存后的聚合始终至少包含一路 Source 和唯一默认预览源，已有 Source ID 保持稳定。

移除 Source 只需满足 Camera 聚合自身约束，不需要额外业务前置条件。

## 2. 范围

### 后端

- 以完整聚合语义处理 `PUT`。
- 校验已有 Source 所有权并计算新增、更新、排序和删除差异。
- 在一个事务更新 Camera、Source 集合和默认源。
- 使受连接字段影响的状态和播放投影失效。

### 前端

- 从 Camera 详情初始化编辑表单。
- 支持 Source 动态增删、排序和默认源选择。
- 提交完整聚合并处理字段错误。
- 成功后刷新列表、详情和受影响播放缓存。

### 不属于本模块

- 独立编辑单一路 Source 的 API。
- 保存前 RTSP 连接测试。
- 可靠异步基础设施清理。

## 3. API

```http
PUT /api/v1/cameras/6f9619ff-8b86-4e4f-9f68-bb3f8f6f4f21
Content-Type: application/json
```

请求中的 `sources` 是保存后的完整集合：

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
      "name": "通道 1 子码流",
      "url_suffix": "Streaming/Channels/102",
      "is_default_preview": true
    },
    {
      "name": "通道 2 主码流",
      "url_suffix": "Streaming/Channels/201",
      "is_default_preview": false
    }
  ]
}
```

语义：

- `3f2504e0-4f89-41d3-9a0c-0305e82c3301` 保留并更新。
- 请求中未出现的已有 Source 被删除。
- 没有 `source_id` 的项是新增 Source。
- 数组顺序是保存后的 Source 顺序。
- 唯一 `is_default_preview=true` 项成为默认源。

成功返回 `200`、`Cache-Control: no-store` 和与 [Camera 详情](../04-camera-detail/README.md) 相同的 CameraDetail。

## 4. 校验规则

基础字段和 Source 字段规则与创建一致，并增加：

| 场景 | 字段/code |
| --- | --- |
| 已有项不是标准 UUID | `sources[i].source_id/INVALID_UUID` |
| `source_id` 不属于当前 Camera | `sources[i].source_id/SOURCE_NOT_OWNED_BY_CAMERA` |
| 请求内重复 `source_id` | 第二项 `sources[i].source_id/DUPLICATE_SOURCE_ID` |
| 规范化后缀重复 | 第二项 `sources[i].url_suffix/DUPLICATE_SOURCE_SUFFIX` |
| 没有 Source | `sources/SOURCE_REQUIRED` |
| 没有默认源 | `sources/DEFAULT_SOURCE_REQUIRED` |
| 多个默认源 | 后续默认项 `is_default_preview/MULTIPLE_DEFAULT_SOURCES` |

禁止客户端修改 `camera_id/created_at/updated_at/sort_order`。请求出现这些只读字段时返回 `422 UNKNOWN_FIELD`。

## 5. Source 差异规则

- 以稳定 `source_id` 判断保留、更新和删除，不使用数组下标识别已有 Source。
- Source 改名不改变 ID 或 MediaMTX Path 名称。
- `url_suffix` 改变时保留 ID，提交后尽力更新或重建该 Source 的 MediaMTX Path；在 `available/online` 同时为 `true` 前状态为 `OFFLINE`。
- Camera `ip_address/rtsp_port/username/password` 任一改变时，提交后尽力更新或重建全部所属 Source 的 MediaMTX Path。
- 连接字段变化后，由它们生成的所有 RTSP URL 立即使用新值。
- 被删除 Source 的播放映射在事务提交后尽力释放。
- 尽力释放失败不回滚数据库更新；MVP 记录脱敏日志和指标，不进入可靠重试队列。

## 6. 后端事务流程

1. 读取并锁定 Camera 聚合。
2. 不存在返回 `404 CAMERA_NOT_FOUND`。
3. 验证请求字段、Source 所有权、重复项和默认源约束。
4. 计算 Source 新增、更新、删除和新顺序。
5. 在一个事务更新 Camera，执行 Source 差异并设置默认 Source ID。
6. 更新聚合 `updated_at`；未改变的 Source 保留原 `created_at`。
7. 提交后尽力更新连接信息变化的播放映射，并释放已删除 Source 的映射。
8. 读取一次 `/paths/list` 投影最新状态并返回详情；Control API 失败时按 `OFFLINE` 返回。

任何异常都不得产生半更新聚合。若提交后的投影清理失败，配置更新仍成功，详情暂时返回降级状态。

## 7. 前端编辑行为

- 从最新 CameraDetail 初始化表单。
- 已有 Source 行保存隐藏的稳定 `source_id`；拖动排序不得改变 ID。
- 新增行不生成客户端正式 Source ID，可使用仅限 UI 的临时 key。
- 删除最后一路 Source 被禁用。
- 删除当前默认源时，自动选中删除后第一路 Source，并向用户展示变化。
- 离开有未保存修改的表单前二次确认。
- 保存期间禁用再次提交；失败保留全部输入和 Source 顺序。
- 成功后失效 `cameras`、当前 `camera` 和所有已删除或连接信息变化 Source 的 `playback`。

服务端不执行版本比较；两个更新先后提交时，最后完成提交的合法请求成为当前聚合。

## 8. 错误与恢复

| 场景 | 响应/行为 |
| --- | --- |
| Camera 不存在 | `404 CAMERA_NOT_FOUND`，返回列表 |
| 字段或 Source 约束错误 | `422 VALIDATION_ERROR`，映射表单 |
| 数据库不可用 | `503 DATABASE_UNAVAILABLE`，保留草稿 |
| 提交后状态/播放清理失败 | 更新仍 `200`，投影降级并记录告警 |

## 9. Fixture

至少提供：

- 仅改 Camera 名称。
- 新增 Source、删除 Source、重命名 Source 和重新排序。
- 删除默认 Source 后指定新默认源。
- 修改 Camera 连接字段导致全部状态失效。
- Source 不属于 Camera、重复 ID 和重复后缀。
- 播放映射更新或释放失败。

## 10. 独立验收

1. 仅修改名称时 Source ID、顺序和默认源保持不变。
2. 新增 Source 获得新 ID，保留项 ID 不变，缺失项被删除。
3. Source 重排只改变顺序，不改变 ID。
4. 删除 Source 在满足聚合约束时即可成功。
5. 连接信息变化后 RTSP URL 更新，MediaMTX Path 在 `available/online` 同时为 true 前显示 `OFFLINE`。
6. 非本 Camera Source ID、重复后缀和非法默认源返回精确字段错误。
7. 数据库事务失败时所有字段和 Source 都保持原值。
8. 日志和错误体不包含旧密码或新密码。

## 11. Definition of Done

- 完整聚合更新、Source 差异逻辑和事务已实现。
- 编辑表单、动态 Source、默认源和未保存提醒已实现。
- 状态/播放失效边界有测试且不会回滚配置更新。
- 可用 Fixture 独立演示所有更新路径。
