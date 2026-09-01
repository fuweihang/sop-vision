# 03｜Camera Card 预览

## 任务目标

为 `/cameras` 的在线 Camera Card 增加实时预览。Card 只有在页面可见、进入视口且列表提供非空
`whep_url` 时才持有 Stream Lease；离开视口、页面隐藏、切页、搜索变化或卸载时及时释放。同一 Source
在 Card 和 Detail 中同时出现时复用一个 `WhepSession` 和 `MediaStream`。

## 当前上下文与前置条件

- [Camera 列表 API](../../../../modules/cameras/camera-list.md)和
  [02｜Camera 列表页面](../02-camera-list-page/README.md)必须已经实施完成并通过验证。
- 开始实施前以当前 Camera Card、列表 Query、Route 测试和生成类型为准，不重新实现 01、02 的数据
  获取、搜索分页或页面状态。
- 先阅读 [WHEP 浏览器播放](../../../../modules/cameras/whep-player.md)和现有
  `frontend/src/features/video/stream-session/`、`video-surface/` 实现及测试。
- `StreamSessionManager` 已按 `source_id` 缓存 Session 并引用计数；`useStreamSession(null, null)` 不占用
  Lease；`VideoSurface` 支持独立 video DOM、`cover` 模式和 HTML overlay。
- Detail 的临时 Source 只属于详情页面，不修改 Backend 默认源。Card 始终使用列表响应中的
  `default_preview_source`。

## 实施范围

### 视口与页面可见性

- 每张 Card 使用 IntersectionObserver 观察媒体区域。使用一个共享的非零可见阈值（建议 `0.25`）和
  `rootMargin: "0px"`；集中为可测试常量，不为滚动抖动增加固定冷却计时器。
- Card 只有同时满足以下条件才 acquire：文档可见、Card 达到阈值、默认 Source `whep_url` 非空。
- `whep_url=null` 时不 acquire，也不渲染一个没有媒体来源的 video；展示现有状态和明确的不可预览
  占位内容。
- 页面变为 hidden 时释放全部 Card Lease。恢复 visible 时依据 Observer 保存的当前相交状态重新计算，
  只让仍在视口内的 Card acquire。
- 切页、搜索变化和路由离开会卸载旧 Card；Observer 必须 disconnect，Lease 必须 release。React Strict
  Mode 重挂载不得产生重复 Session 或负引用。

### Card 播放与共享

- 有 `whep_url` 的 Card 复用 `useStreamSession(source_id, whep_url)` 和 `VideoSurface`，使用
  `objectFit="cover"`，不复制 reader、Session 或 video hooks。
- Card video 始终静音、音量为 0、自动播放，不显示详情的 Source Select、播放、刷新、音量或全屏
  controls。
- Card overlay 只增加设备名称、在线状态和带文字的 `LIVE`；状态不能只依赖颜色表达，overlay 不阻断
  Card 详情 Link 的指针或键盘交互。
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

1. 实现可复用、可测试的 Card 视口状态 hook，封装 IntersectionObserver 注册、阈值、清理和测试环境
   适配；业务 hook 不直接创建媒体 Session。
2. 实现文档可见性状态，组合为单一 `shouldAcquire`。验证 hidden/visible、相交变化和组件卸载时不会
   留下过期状态或监听器。
3. 扩展 Camera Card 媒体区域：无 URL 渲染非 video 占位；有 URL 时装配 `useStreamSession`、
   `VideoSurface cover`、静音播放和非交互 overlay。
4. 增加 Card 组件测试：在线/离线、进入/离开视口、页面隐藏/恢复、列表刷新 URL 不变与变化、切页、
   搜索变化、卸载和 Strict Mode。
5. 扩展 Stream Session 集成测试：Card+Card、Card+Detail 共享一个 reader，逐个释放保持 Track，最后
   释放清空 Session 与 `srcObject`。
6. 使用现有 synthetic WHEP 双流进行浏览器冒烟测试，确认滚动只连接可见 Card、Card 始终静音、进入
   详情可共享同一路流且返回列表后没有遗留 Lease。
7. 完成 08 文档收尾：更新 Cameras 模块当前能力和排障说明，新增最终 Card 预览变更记录，移除已完成
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
Source 和开发命令。至少检查可见/不可见 Card、页面隐藏/恢复、Card 与 Detail 同源共享、路由离开和
最后一个消费者释放。

## 完成标准

- `whep_url=null` 或未进入视口的 Card 不创建 reader，不渲染无来源 video。
- 页面隐藏、切页、搜索变化和卸载会释放对应 Lease；恢复时只有仍可见 Card 重新 acquire。
- 同一路 Source 的多个 Card 或 Card+Detail 只有一个 reader 和 MediaStream。
- 释放单个消费者不停止其他消费者；最后释放后 Session cache、Track 和 `srcObject` 全部清理。
- Card 使用 `cover`、始终静音、没有详情 controls，LIVE 与状态同时有可读文字。
- 列表非媒体字段刷新不重建 Session；Source ID 或 WHEP URL 改变时正确切换。
- Frontend 全套检查、敏感数据检查和 synthetic WHEP 浏览器冒烟测试通过。
- Cameras 当前能力与变更记录已更新，08 已按上级计划要求移除，可以进入 09。

## 与下一任务的衔接

08 完成后进入 [09｜更新 Camera 与切换默认源](../../09-camera-update-default-source/README.md)。09 应复用
本任务验证过的共享 Session 和 Card 默认 Source 规则：默认源 PATCH 成功后失效列表，Card 只跟随最新
列表响应，不自行选择备用 Source。
