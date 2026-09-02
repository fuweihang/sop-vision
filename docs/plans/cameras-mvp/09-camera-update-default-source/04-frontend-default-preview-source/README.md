# 04｜Frontend 默认源与播放器联动

## 任务目标

启用 Camera 详情 Source 表格中的默认源单选，通过
`PATCH /api/v1/cameras/{camera_id}/default-preview-source` 持久化选择，并保证 Camera Card、详情
默认/临时选择和共享 WHEP Session 只在实际媒体来源变化时切换。

## 当前上下文 / 前置条件

- [01｜Backend Camera 完整更新](../01-backend-camera-update/README.md)、
  [02｜Backend 默认预览源切换](../02-backend-default-preview-source/README.md)和
  [03｜Frontend Camera 编辑 Dialog](../03-frontend-camera-edit/README.md)必须已经完成并通过验证。
- 开始前读取 [09 总计划](../README.md)、[Camera 详情](../../../../modules/cameras/camera-detail.md)、
  [Camera 列表](../../../../modules/cameras/camera-list.md)和
  [WHEP 浏览器播放](../../../../modules/cameras/whep-player.md)，并以任务 03 后的实际组件和测试为准。
- 当前 `CameraSources` 已渲染默认源 RadioGroup，但整体禁用。现有
  `resolveCameraPreviewSource` 已区分 `{kind: "default"}` 与 `{kind: "temporary"}`，详情和
  Card 已通过 `source_id+whep_url` 使用共享 Stream Session Manager。
- `setDefaultPreviewSource` Client 和响应类型已存在；任务 02 已交付真实 Backend handler。

## 实施范围

### PATCH 交互与错误

- 启用 Source 表格 RadioGroup。在线、离线或没有 `whep_url` 的 Source 都可选，因为默认配置不依赖
  当前媒体状态。
- 单选不做乐观更新；发请求后继续显示提交前的默认 ID，并禁用全部单选项，防止并发 PATCH。
- Mutation `retry=false`。成功后显示可感知反馈，并失效 `cameras` 前缀与当前 `camera`，由最新
  列表和详情响应决定最终 UI。
- `404 CAMERA_NOT_FOUND`、`422 VALIDATION_ERROR` 和
  `500 CAMERA_AGGREGATE_INVALID` 作为确定失败，恢复可操作状态并继续显示旧默认 ID。
- Transport、意外/不符合契约的响应、`503 DATABASE_UNAVAILABLE` 和其他服务端 `5xx` 作为结果
  未知。不自动重发、不保留错误的乐观结果；立即失效并重新获取列表和当前详情，用服务端最新读取
  结果确认默认 ID。重新读取失败时持续显示结果未知。
- Mutation 状态不得持久化或记录请求/响应；错误提示只使用稳定 status/code 和固定中文文本。

### 列表、详情和 Lease

- Camera Card 只消费最新列表响应的 `default_preview_source.source_id+whep_url`。新默认 Source
  的 `whep_url=null` 时不 acquire，不请求 CameraDetail，也不选择其他 Source。
- Detail 当前选择是 `{kind: "default"}` 时，最新详情返回后重新执行“Backend 默认源可播放时优先，
  否则响应顺序中的第一路可播放源”；全部不可播放时不 acquire。
- Detail 当前选择是 `{kind: "temporary"}` 时，默认源 PATCH 成功或详情默认 ID 刷新都不改变当前
  Session。只有临时 Source 被删除、变为离线或失去 `whep_url` 时，才退出临时选择并按默认规则回退。
- 用户已经停止详情预览时，默认源刷新只更新已解析选择，不能自行恢复预览。
- Card 或 Detail 仅在实际 Source ID 或 `whep_url` 改变时 release 旧 Lease 并按需 acquire；相同
  Source 和 URL 的名称、默认标记或状态文字变化不重建 Session。
- 同一 Source 被 Card 和 Detail 消费时继续共享一个 reader 和 MediaStream；单个消费者 release 不
  停止 Track，最后一个引用释放后才关闭 Session。

## 明确不做

- 不修改 Camera 编辑 Dialog、PUT 请求、Source 配置或排序。
- 不修改 Backend PATCH、MediaMTX Path、Stream Gateway 或对账。
- 不让 Card 请求详情、选择备用 Source、显示 Detail controls 或发送 PATCH。
- 不为结果未知增加自动重试、轮询协议、幂等键或乐观回滚框架。
- 不重构 Stream Session Manager，除非测试证明现有实现违反已记录的共享规则；修复只能针对已确认
  缺陷，不能创建第二套 Session cache。
- 不执行真实 IPC、Codec、HTTPS/NAT、长时间和容量门禁；这些属于
  [11｜发布门禁](../../11-release-gates/README.md)。
- 本任务完成后不更新长期能力文档或移除 09；统一由任务 05 处理。

## 实施步骤

1. 为默认源 PATCH 新增窄用途 Mutation 状态和确定失败/结果未知映射，复用任务 03 已存在且行为完全
   相同的纯分类逻辑；不建立通用写框架。
2. 启用 `CameraSources` RadioGroup，接通提交禁用、错误反馈和列表/详情 Query 失效。
3. 扩展详情组合状态测试，覆盖默认选择、临时选择、停止预览、离线默认源和全部不可播放。
4. 扩展 Card 与详情组件测试，证明只在实际 Source ID 或 URL 变化时切换 Lease。
5. 扩展 Stream Session 集成测试，验证 Card+Detail 同源共享、逐个 release 和最后引用清理。
6. 使用现有双路 synthetic WHEP Source 做浏览器冒烟，确认默认源切换、临时选择保留、离线默认源和
   两路画面/Session 变化。

## 验证方式

```bash
# 仓库根目录
bash scripts/check-cameras-contracts.sh
bash scripts/check-cameras-sensitive-data.sh

# frontend/
pnpm vendor:check
pnpm test
pnpm lint
pnpm format:check
pnpm build
```

浏览器冒烟使用 [WHEP 浏览器播放](../../../../modules/cameras/whep-player.md)已有的双路 synthetic
Source。至少检查默认选择切换、离线默认源、临时选择不变、停止预览不自启、Card/Detail 同源共享和
最后一个 Lease 释放。

## 完成标准

- 默认源单选可以持久化在线或离线 Source，提交期间不可重复操作，且没有错误的乐观状态。
- 成功、确定失败和结果未知分别呈现正确行为，列表与详情按最终服务端响应刷新。
- Card 只跟随列表默认 Source；Detail 默认/临时选择和停止意图符合既有播放器规则。
- 相同实际 ID+URL 不重建 Session，变化时旧 Lease 正确释放并 acquire 新源；共享引用计数无泄漏。
- Frontend 全套检查、契约与敏感数据检查、synthetic WHEP 浏览器冒烟全部通过。

## 与下一任务的衔接

下一步执行 [05｜09 集成验收与文档收尾](../05-integration-docs/README.md)。任务 05 将以 01–04 的实际
代码、契约和测试为输入执行组合验收；本任务不得提前移除 09 或把 synthetic 验收扩大成发布门禁。
