# 06｜切换默认预览源

> 前置：[Cameras 基础契约](../01-foundation/README.md)、[Camera 详情](../04-camera-detail/README.md)  
> 交付：默认源 PATCH API 和详情页单选交互

## 1. 完成目标

用户无需打开完整编辑表单，即可在 Camera 详情页把任意所属 Source 设置为唯一默认预览源。

切换只修改 `default_preview_source_id` 和更新时间，不修改 Source 顺序、连接信息或运行状态。

## 2. 范围

### 后端

- 校验 Camera 和 Source 所有权。
- 原子更新默认 Source 和 `updated_at`。
- 返回轻量更新结果。

### 前端

- 在 Source 列表中提供单选默认源操作。
- 展示提交中、成功和失败状态。
- 更新列表、详情和默认预览区域。

### 不属于本模块

- 修改 Source 配置或顺序。
- 判断 Source 是否在线。
- 创建、停止或重建播放会话。

## 3. API

Foundation 已以 `operation_id=setDefaultPreviewSource` 注册该路径。进入本切片时必须复用原
Router 和 DTO，不得新建平行端点。

```http
PATCH /api/v1/cameras/6f9619ff-8b86-4e4f-9f68-bb3f8f6f4f21/default-preview-source
Content-Type: application/json
```

```json
{
  "source_id": "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
}
```

成功：

```http
HTTP/1.1 200 OK
```

```json
{
  "camera_id": "6f9619ff-8b86-4e4f-9f68-bb3f8f6f4f21",
  "default_preview_source_id": "3f2504e0-4f89-41d3-9a0c-0305e82c3301",
  "updated_at": "2026-08-19T03:10:00Z"
}
```

## 4. 业务规则

- `source_id` 必须存在且属于 URL 中的 Camera。
- Source 为 `OFFLINE` 时仍允许成为默认源；状态只影响当前能否预览。
- 成功切换后恰好一路 Source 的 `is_default_preview=true`。
- 切换不改变 Source 状态、顺序、RTSP 配置或当前浏览器播放器。
- 前端收到成功结果后由预览组件决定是否停止旧会话并加载新默认源。

## 5. 后端处理流程

1. 读取并锁定 Camera。
2. Camera 不存在返回 `404 CAMERA_NOT_FOUND`。
3. 查询 `source_id` 是否属于当前 Camera。
4. 不存在或不属于当前 Camera 返回 `422 SOURCE_NOT_OWNED_BY_CAMERA`，字段为 `source_id`。
5. 更新 `default_preview_source_id` 和 `updated_at`。
6. 返回最新结果。

更新必须为单条原子聚合写入或包含在一个数据库事务中。

## 6. 前端交互

- 当前默认 Source 显示已选中的单选控件和“默认预览”标签。
- 用户选择其他 Source 后立即发起 PATCH；提交期间禁用所有默认源单选项。
- 成功后更新当前详情的默认标记，并失效 `cameras` 和当前 `camera`。
- 若详情预览正在播放旧默认源，先正常关闭旧播放器，再由用户设置的预览策略决定是否启动新源。
- 其他失败恢复原单选状态并提供重试，不保留错误的乐观状态。

## 7. 错误与恢复

| 场景 | 响应 |
| --- | --- |
| Camera 不存在 | `404 CAMERA_NOT_FOUND` |
| Source 不存在或不属于 Camera | `422 SOURCE_NOT_OWNED_BY_CAMERA` |
| 数据库不可用 | `503 DATABASE_UNAVAILABLE` |

不得以 Source 离线为由返回业务错误。

## 8. Fixture

至少提供：

- 两路 Source 正常切换。
- 切换到 `ONLINE/OFFLINE` Source。
- Source 不属于 Camera 和 Camera 不存在。
- 数据库写入失败。

## 9. 独立验收

1. 任意所属 Source 都可设为默认源，不受连接状态影响。
2. 切换后只有一路 Source 为默认，`updated_at` 被更新。
3. 非本 Camera Source 返回准确字段错误。
4. 成功后列表和详情缓存得到更新或失效。
5. 切换请求不会修改 Source 状态、配置或顺序。

## 10. Definition of Done

- PATCH 路由、所有权校验和原子更新已实现并测试。
- `setDefaultPreviewSource` 的占位 `NotImplementedError` 已由真实 Service 调用替换。
- 详情页默认源单选、提交反馈和失败回滚已实现。
- 可使用 Fixture 独立演示成功和全部错误路径。
