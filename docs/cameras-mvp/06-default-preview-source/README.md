# 06｜切换默认预览源

> 前置：[Foundation](../01-foundation/README.md)、[详情](../04-camera-detail/README.md)
>
> 交付：`PATCH /api/v1/cameras/{camera_id}/default-preview-source`
> （`setDefaultPreviewSource`）和详情页单选交互

## 契约与行为

```json
{ "source_id": "3f2504e0-4f89-41d3-9a0c-0305e82c3301" }
```

成功返回 `200`：

```json
{
  "camera_id": "6f9619ff-8b86-4e4f-9f68-bb3f8f6f4f21",
  "default_preview_source_id": "3f2504e0-4f89-41d3-9a0c-0305e82c3301",
  "updated_at": "2026-08-19T03:10:00Z"
}
```

后端锁定 Camera，确认目标 Source 属于该聚合，原子更新默认 ID 和 `updated_at`。Camera 不存在
返回 `404 CAMERA_NOT_FOUND`；Source 不存在或不属于 Camera 返回字段
`source_id/SOURCE_NOT_OWNED_BY_CAMERA`；数据库不可用返回 `503 DATABASE_UNAVAILABLE`。

离线 Source 也可以设为默认。切换不改变 Source 配置、顺序、状态或当前浏览器会话；成功后
必须恰好一路 Source 的派生 `is_default_preview` 为 true。

## 前端与验收

- 当前 Source 显示选中状态和“默认预览”标签；提交期间禁用全部单选项。
- 成功后失效 `cameras` 和当前 `camera`；若旧默认源正在播放，先正常关闭旧会话，再由页面
  预览策略决定是否加载新源。
- 失败恢复原单选状态，不保留错误的乐观结果，并提供重试。
- 验收覆盖切换到在线/离线 Source、非本 Camera Source、不存在 Camera、数据库失败，以及
  Source 配置/顺序/状态均未被修改。
