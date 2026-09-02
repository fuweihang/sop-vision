# 03｜Frontend Camera 编辑 Dialog

## 任务目标

在 Camera 详情页启用“编辑摄像头”，交付完整 Camera/Source 编辑 Dialog。用户可以修改连接字段，
新增、删除、重排 Source 并选择唯一默认源；表单草稿不被详情轮询覆盖，确定失败和结果未知都有明确
处理，未保存修改离开前必须确认。

## 当前上下文 / 前置条件

- [01｜Backend Camera 完整更新](../01-backend-camera-update/README.md)和
  [02｜Backend 默认预览源切换](../02-backend-default-preview-source/README.md)必须已经实施并通过验证。
  开始时以最终 OpenAPI、生成类型、Client 和错误响应为准。
- 开始前读取 [09 总计划](../README.md)、[Camera 详情](../../../../modules/cameras/camera-detail.md)、
  [WHEP 浏览器播放](../../../../modules/cameras/whep-player.md)以及设计系统的
  [Agent Guidelines](../../../../design-system/agent-guidelines.md)、
  [Page Patterns](../../../../design-system/specs/page-patterns.md)和
  [Interaction and Accessibility](../../../../design-system/specs/interaction-accessibility.md)。
- 当前详情页每 15 秒刷新 CameraDetail，编辑按钮处于禁用状态；详情、预览选择和 Lease 生命周期已
  存在，编辑 Dialog 不得重新实现播放器。
- Camera 创建 Dialog 已使用 React Hook Form、Zod、Field、Input、RadioGroup、ScrollArea、Alert、
  Spinner、Sonner 和服务端字段错误映射。应复用适合共享的字段和纯转换逻辑，但不能让创建和编辑
  相互接受错误的 DTO 字段。
- TanStack Router 当前版本提供 `useBlocker` resolver 和 `enableBeforeUnload`；应用内确认使用现有
  AlertDialog，不使用 `window.confirm()`。

## 实施范围

### 表单数据与 Source 操作

- Dialog 每次打开时只从当时详情页正在显示的 CameraDetail 初始化一次。Dialog 打开后的 15 秒详情
  刷新可以更新页面和播放器，但不得重置表单，无论表单是否已变脏。
- 连接字段包含 `name/ip_address/rtsp_port/username/password`。密码沿用详情响应中的当前值初始化，
  使用密码输入行为，不在提示、通知或错误摘要中回显。
- 已有 Source 行保存 API `source_id`；新增行的 `source_id` 保持缺省，只使用 React Hook Form
  `useFieldArray` 提供的 UI key。提交 DTO 不得发送 UI key。
- 新增 Source 固定追加到末尾。最后一路删除按钮禁用；删除默认 Source 时选择删除后剩余数组第一项。
- MVP 使用有可访问名称的上移/下移按钮重排，首项上移和末项下移禁用；不引入拖拽库。移动只改变
  数组顺序，不改变已有 Source ID 或默认选择。
- 表单始终保持至少一路 Source 和恰好一路默认；Frontend 校验用于即时反馈，Backend 仍是最终规则。

### 提交、错误与缓存

- 使用现有 `updateCamera` Client 发 PUT。Mutation `retry=false`、`gcTime=0`，调用方只消费成功/
  失败，不让含密码、后缀和 CameraDetail 的 Mutation data/variables 在关闭后继续保留。
- `404 CAMERA_NOT_FOUND`、`422 VALIDATION_ERROR` 和
  `500 CAMERA_AGGREGATE_INVALID` 作为确定失败；所有失败都保留输入、默认选择和顺序。
- 可见字段的 `422` 逐项映射到 React Hook Form，并聚焦首个可定位字段。隐藏 `source_id` 的
  `INVALID_UUID/SOURCE_NOT_OWNED_BY_CAMERA/DUPLICATE_SOURCE_ID` 显示在对应 Source 行；无法安全
  定位的字段错误进入表单级 Alert。
- Transport、意外/不符合契约的响应、`503 DATABASE_UNAVAILABLE` 和其他服务端 `5xx` 作为“更新
  结果未知”。不自动重发；保留表单，立即失效并重新获取 `cameras` 与当前 `camera`，提示数据库
  可能已经提交。重新读取无论成功或失败都不得重置、比较或覆盖当前草稿，也不得据此自动判定 PUT
  成功或关闭 Dialog；读取结果只更新 Query cache，结果未知提示持续保留。
- 结果未知后允许用户继续修改当前草稿。再次点击保存只打开独立的 AlertDialog，说明上一请求可能已经
  提交、本次操作会使用当前表单发送一条新的完整更新；取消确认时保留表单且不得发送 PUT，明确确认后
  才发送恰好一条新请求。该确认与丢弃未保存修改、路由离开确认使用同一现有 primitive，但必须区分
  状态和确认动作。
- 成功后清除 dirty 状态，关闭并回收 Dialog/Mutation 状态，显示成功通知，失效 `cameras` 和当前
  `camera`。不直接把 PUT CameraDetail 写入 Query cache，也不由编辑表单启动或切换 Session。

### 未保存修改与提交状态

- 未修改表单可以直接通过取消、关闭按钮、Escape 或 Dialog 外点击关闭。
- 表单变脏后，上述关闭入口都先打开 AlertDialog，说明未保存修改会丢失。选择留下时保留表单并把
  焦点恢复到原 Dialog；确认丢弃后才重置并关闭。
- Dialog 打开且表单变脏时，应用内路由跳转使用 `useBlocker({ withResolver: true })` 接入同样的
  AlertDialog 决策；浏览器刷新、关闭标签页或跨站离开使用 `enableBeforeUnload`。
- 提交期间禁用输入、默认源、增删、排序、取消、关闭和重复提交，并阻止应用内离开；浏览器离开继续
  使用原生 beforeunload 防护。保存按钮保持尺寸并显示可感知的加载状态。
- 所有 blocker、beforeunload、Dialog 和 Mutation 状态在关闭或卸载时清理，不能影响后续详情页面或
  其他路由。

## 明确不做

- 不启用详情 Source 表格中用于独立 PATCH 的默认源单选；由任务 04 实现。
- 不改变详情默认/临时预览选择、WHEP Session、Card 或 Stream Session Manager。
- 不增加拖拽、自动保存、localStorage/IndexedDB 草稿、跨页面恢复、版本冲突 UI 或通用表单框架。
- 不新建 UI primitive，不覆盖现有 shadcn/Base UI 文件，不使用 `window.confirm()`。
- 不修改 Backend 更新规则或 Camera 删除。
- 本任务完成后不更新长期能力文档或移除 09；统一由任务 05 处理。

## 实施步骤

1. 基于最终生成类型新增编辑表单 Schema、初始化转换、PUT DTO 转换和安全字段错误映射测试。
2. 在不混淆创建/更新 DTO 的前提下复用或提取连接字段与 Source 字段组件，补充 Source ID、上移和
   下移能力。
3. 实现受控编辑 Dialog，接通详情按钮、一次初始化、提交禁用、成功反馈和 Query 失效。
4. 实现确定失败与结果未知映射，确保 Mutation 状态立即回收、Query 重新读取不影响草稿、结果未知
   提示持续保留，且再次保存经过独立确认后才发送新请求。
5. 用现有 AlertDialog 和 `useBlocker` 实现 Dialog 关闭、应用内路由及 beforeunload 防护。
6. 增加表单纯函数、错误映射、Dialog、路由阻止、详情轮询重渲染、提交状态和敏感数据测试；覆盖结果
   未知后的重新读取成功/失败都不重置表单，确认前零新请求、取消确认零新请求以及确认后恰好一条新
   请求。
7. 检查窄屏单列、Dialog Body 内滚动、Footer 常驻、长 Source 名称、键盘顺序和 Focus Restore。

## 验证方式

```bash
# 仓库根目录
bash scripts/check-cameras-contracts.sh
bash scripts/check-cameras-sensitive-data.sh

# frontend/
pnpm test
pnpm lint
pnpm format:check
pnpm build
```

另外使用浏览器检查键盘完成打开、编辑、增删、排序、错误修正、取消丢弃和路由离开确认；紧凑视口
不能出现页面级水平滚动，焦点 Ring 不能被 ScrollArea 裁切。

## 完成标准

- 详情编辑按钮可用，Dialog 能完整提交 Camera 和 Source 集合，已有 ID、新增项和数组顺序正确。
- 删除最后一路、删除默认源、上移/下移及唯一默认规则都有确定测试。
- 详情轮询不覆盖已打开表单；成功正确关闭并刷新列表/详情，失败保留全部草稿。
- 确定失败、结果未知、无自动重试和敏感 Mutation 回收行为均通过测试。
- 结果未知后的 Query 重新读取只更新缓存且不影响草稿；再次保存的独立确认在确认前不发送请求，确认
  后只发送一条使用当前表单值的新 PUT。
- Dialog 关闭、应用内跳转和浏览器离开保护只在需要时启用，提交期间无法重复操作或离开。
- Frontend 全套检查、契约检查、敏感数据检查和浏览器键盘/Reflow 冒烟通过。

## 与下一任务的衔接

下一步执行 [04｜Frontend 默认源与播放器联动](../04-frontend-default-preview-source/README.md)。下一任务
只启用详情 Source 表格中的独立 PATCH 交互，并消费刷新后的列表/详情数据；不得把编辑 Dialog 的
PUT 默认选择与 PATCH 单选合并成一次请求或共享乐观状态。
