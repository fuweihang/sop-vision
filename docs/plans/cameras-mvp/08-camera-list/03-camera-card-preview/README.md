# 03｜Camera Card 预览

## 任务目标

为 `/cameras` 的在线 Camera Card 增加实时预览。Card 挂载且列表提供非空 `whep_url` 时持有 Stream
Lease；`whep_url` 变为 `null`、搜索或翻页替换 Card、离开路由或卸载时及时释放。同一 Source 在 Card
和 Detail 中同时出现时复用一个 `WhepSession` 和 `MediaStream`。

## 当前上下文与前置条件

- [Camera 列表](../../../../modules/cameras/camera-list.md)API 和页面能力必须已经实施完成并通过验证。
- 开始实施前以当前 Camera Card、列表 Query、Route 测试和生成类型为准，不重新实现 01、02 的数据
  获取、搜索分页或页面状态。
- 先阅读 [WHEP 浏览器播放](../../../../modules/cameras/whep-player.md)和现有
  `frontend/src/features/video/stream-session/`、`video-surface/` 实现及测试。
- `StreamSessionManager` 已按 `source_id` 缓存 Session 并引用计数；`useStreamSession(null, null)` 不占用
  Lease；`VideoSurface` 支持独立 video DOM、`cover` 模式和 HTML overlay。
- Detail 的临时 Source 只属于详情页面，不修改 Backend 默认源。Card 始终使用列表响应中的
  `default_preview_source`。

## 实施范围

### Card 挂载与输入生命周期

- Card 挂载且默认 Source `whep_url` 非空时 acquire。离开视口或文档变为 hidden 都不改变 Lease，
  不增加 IntersectionObserver、Page Visibility 监听、可见比例阈值、防抖或冷却计时器。
- `whep_url=null` 时不 acquire，也不渲染一个没有媒体来源的 video；展示现有状态和明确的不可预览
  占位内容。
- 搜索或翻页后，不再出现在结果中的旧 Card 会卸载并 release；如果同一个 `camera_id` 仍保留在新结果
  中，且 `source_id+whep_url` 未变化，则继续使用原 Lease，不因查询参数变化强制重建 Session。
- 路由离开和组件卸载必须 release。React Strict Mode 重挂载不得产生重复 Session 或负引用。

### Card 播放与共享

- 有 `whep_url` 的 Card 复用 `useStreamSession(source_id, whep_url)` 和 `VideoSurface`，使用
  `objectFit="cover"`，不复制 reader、Session 或 video hooks。
- Card video 始终静音、音量为 0、自动播放，不显示详情的 Source Select、播放、刷新、音量或全屏
  controls。
- 保留现有 Card 结构：媒体 overlay 显示默认 Source 名称，Camera 名称和 Camera 状态继续显示在媒体区
  下方，不在 overlay 重复。媒体 overlay 另外显示列表响应中的默认 Source 状态，以及当前浏览器
  Session 状态；两类状态都必须有可读文字，不能只依赖颜色表达。
- Session 状态固定投影为：`idle/closed` 显示“等待预览”，`connecting` 显示“正在连接”，`playing`
  显示 `LIVE`，`reconnecting` 显示“正在重连”，`failed` 显示“连接失败”。Card 不为失败状态增加刷新
  或重试控件；reader 的既有重连行为保持不变。
- overlay 不阻断 Card 详情 Link 的指针或键盘交互。
- Card 和 Detail 各自保留独立 video DOM、muted/volume 与 overlay；同一 `source_id+whep_url` 通过全局
  `StreamSessionManager` 共享一个 Session 和 MediaStream。
- 一个消费者 release 不停止其他消费者仍使用的 Track；最后一个消费者 release 后关闭 Session、停止
  Track、清除 Manager 缓存并清空相关 video `srcObject`。
- 列表 15 秒刷新只在实际 `source_id` 或 `whep_url` 改变时切换 Lease；仅 Camera 名称、计数或状态文字
  更新不得重建相同媒体 Session。

## 明确不做

- 不给 Card 增加 Detail controls、音量操作、临时切源、网页全屏或浏览器全屏。
- 不在 Card 中请求 CameraDetail，不选择 Backend 未返回的备用 Source，也不发送默认源 PATCH。
- 不修改 `StreamSessionManager` 的公共模型，除非测试证明现有实现无法满足多个消费者的既定规则；不得
  为 Card 创建第二套 Session cache。
- 不实现 Detection overlay、告警摘要、WebRTC Stats、并发会话上限或自适应码流。
- 不以 jsdom 测试代替 11 的真实部署容量、Codec 和长时间连接验收。

## 实施步骤

1. 扩展 Camera Card 媒体区域：无 URL 渲染非 video 占位；有 URL 时装配
   `useStreamSession(source_id, whep_url)`、`VideoSurface cover`、静音播放、Source 名称、Backend
   Source 状态、Session 状态和非交互 overlay。
2. 增加 Card 组件和 Route 测试：在线/离线、页面隐藏、列表刷新 URL 不变与变化、搜索、切页、路由
   离开、卸载和 Strict Mode。页面隐藏不得释放已挂载 Card 的 Lease；搜索和翻页只释放被结果替换并
   卸载的 Card，相同 `camera_id+source_id+whep_url` 保持 Lease。
3. 扩展 Stream Session 集成测试：Card+Card、Card+Detail 共享一个 reader，逐个释放保持 Track，最后
   释放清空 Session 与 `srcObject`。
4. 扩展现有 `whep-player` MSW 场景：列表摘要必须从使用锁定 synthetic WHEP URL 的详情 Fixture 投影，
   让 Card 与 Detail 返回相同的默认 `source_id+whep_url`；不得让 Card 使用普通 Fixture 的
   `media.example.invalid` 地址。使用该场景进行浏览器冒烟测试，确认有 URL 的已挂载 Card 建立连接、
   Card 始终静音、页面隐藏不释放、进入详情可复用同一路流且返回列表后没有遗留 Lease。
5. 完成 08 文档收尾：更新 Cameras 模块当前能力和排障说明，新增最终 Card 预览变更记录，移除已完成
   的 08 计划入口和目录；不得删除 09–11。

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

浏览器冒烟测试使用 [WHEP 浏览器播放](../../../../modules/cameras/whep-player.md)提供的锁定 synthetic
Source 和开发命令。至少检查已挂载 Card 自动连接、页面隐藏后保持连接、Card 与 Detail 同源共享、
搜索或翻页卸载旧 Card、路由离开和最后一个消费者释放。

## 完成标准

- `whep_url=null` 的 Card 不创建 reader，也不渲染 video；已挂载且有 URL 的 Card 持有 Lease，不受
  视口相交比例或页面 hidden 状态影响。
- 搜索或翻页只释放被替换并卸载的 Card；路由离开和组件卸载释放对应 Lease。仍保留在结果中的相同
  `camera_id+source_id+whep_url` 不重建 Session。
- 同一路 Source 的多个 Card 或 Card+Detail 只有一个 reader 和 MediaStream。
- 释放单个消费者不停止其他消费者；最后释放后 Session cache、Track 和 `srcObject` 全部清理。
- Card 使用 `cover`、始终静音、没有详情 controls；保留 Source 名称，Backend Source 状态与 Session
  状态都有可读文字，只有 `playing` 显示 `LIVE`。
- 列表非媒体字段刷新不重建 Session；Source ID 或 WHEP URL 改变时正确切换。
- Frontend 全套检查、敏感数据检查和 synthetic WHEP 浏览器冒烟测试通过。
- Cameras 当前能力与变更记录已更新，08 已按上级计划要求移除，可以进入 09。

## 与下一任务的衔接

08 完成后进入 [09｜更新 Camera 与切换默认源](../../09-camera-update-default-source/README.md)。09 应复用
本任务验证过的共享 Session 和 Card 默认 Source 规则：默认源 PATCH 成功后失效列表，Card 只跟随最新
列表响应，不自行选择备用 Source。
