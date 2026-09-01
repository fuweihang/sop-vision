# 08｜Frontend 视频展示结构整理

> 前置：[Camera 列表](../../../modules/cameras/camera-list.md)、
> [Camera 详情](../../../modules/cameras/camera-detail.md)、
> [WHEP 浏览器播放](../../../modules/cameras/whep-player.md)
>
> 交付：Card 与 Detail 共用的视频展示状态入口和状态 Badge、Session 失败的明确刷新入口、
> 三种操作栏模式，以及按职责整理后的类型和测试文件

## 任务目标

在不改变 WHEP Session、Lease、video DOM 和媒体生命周期规则的前提下，整理 Camera Card 与 Detail
播放器已经落地的展示代码。消除两处重复的状态装配，保证两种播放器持续使用同一状态文字和恢复
规则，让组件参数只能表达有效组合，并修复 Session 失败提示要求刷新却没有直接恢复入口的问题。

本任务主要整理 Frontend 内部结构，只增加一项用户可见修复：Detail 的 Session 失败常驻提示提供
“刷新当前流”按钮。不新增 Camera 业务能力，也不调整 Backend API。

## 当前上下文与前置条件

- Camera Card 已使用列表响应中的 `default_preview_source`，有 `whep_url` 时挂载 `VideoSurface` 并持有
  Lease；无 URL 时不创建 video。页面 hidden 和 Card 离开视口不释放 Lease，搜索、翻页、路由离开、
  URL 变空和组件卸载按现有规则释放。
- Detail 已把开始/停止预览与 video 播放/暂停分开，并使用 `VideoControls` 显示 Session、首帧、播放和
  画面错误。
- `deriveVideoDisplayState` 已是 Card 与 Detail 共用的纯函数。`waiting-frame/live` 依据各自 video DOM
  独立计算，不能写回共享 Session。
- Card 和 `VideoControls` 仍分别读取 `useVideoSurface()`，并重复组装 `hasPresentedFrame`、
  `!paused`、`playbackError` 和 `presentationError`。
- 两处状态 Badge 重复维护 label 和测试属性。未来修改其中一处时，Card 与 Detail 仍有再次不一致的
  风险。
- `VideoControls` 使用 `previewActive` 和 `mediaControlsDisabled` 两个布尔参数，类型允许“预览已停止但
  播放、刷新和音量仍可操作”的无效组合。
- Session 失败文案要求用户刷新当前流，但当前常驻错误提示只有画面超时会显示刷新按钮。

实施前以当前代码、测试和上述模块文档为准，不恢复已经完成的旧 Camera 列表计划，也不重新实现
搜索、分页或 Card 预览生命周期。

## 实施范围

### 共享视频展示状态入口

- 在 `frontend/src/features/video/display-state/` 中维护展示状态纯函数、类型、Hook 和测试，并通过
  `index.ts` 暴露公共入口。
- 保留 `deriveVideoDisplayState` 作为无 React 依赖的纯函数，继续独立测试所有 Session、首帧、暂停和
  错误优先级。
- 增加 `useVideoDisplayState({ sessionStatus, previewActive })`。该 Hook 必须在 `VideoSurface` 内使用，
  统一读取 `hasPresentedFrame`、`paused`、`playbackError` 和 `presentationError`，然后调用纯函数。
- Card 与 Detail 操作栏都改用该 Hook，不再各自复制 `VideoSurface` 到展示状态的字段映射。

### 状态 Badge 与恢复动作

- 增加通用 `VideoDisplayStatusBadge`，只接收有效的 Session 状态和 `VideoDisplayState`，统一渲染
  overlay Badge、展示 label、`data-stream-session-status` 和 `data-video-display-status`。
- `whep_url=null` 的“不可预览”属于 Camera Card 输入规则，继续由 Camera 组件明确渲染，不进入通用
  video 展示状态，也不为通用 Badge 增加 `isUnavailable` 或 nullable 变体。
- `VideoDisplayState` 的错误数据明确给出恢复方式：播放受阻对应 `play`，画面超时和 Session 失败对应
  `reconnect`。无恢复动作的状态不得携带恢复类型。
- `VideoControls` 同时根据错误恢复方式和当前操作栏模式生成可选恢复动作。只有 `interactive` 会向
  `PlaybackFeedback` 提供带回调的 `play` 或 `reconnect` 动作；`read-only` 和 `stopped` 都传入空动作。
- `PlaybackFeedback` 根据传入的恢复动作渲染“继续播放”或“刷新当前流”，不再读取
  `VideoSurfaceContext` 或自行决定当前模式是否允许操作。Session 失败在 `interactive` 下必须提供刷新
  按钮。
- Card 继续只显示状态 Badge 和无文字 Spinner，不增加恢复按钮；恢复动作只由带操作栏的 Detail 使用。

### 明确操作栏模式

- 使用 `mode: "interactive" | "read-only" | "stopped"` 替换 `previewActive` 和
  `mediaControlsDisabled`：
  - `interactive`：预览运行，播放、刷新和音量可操作。
  - `read-only`：预览运行并继续显示 loading/LIVE，但播放、刷新和音量不可操作。
  - `stopped`：显示已停止，播放、刷新和音量不可操作。
- 网页全屏和浏览器全屏保持现有行为，不因 `read-only` 或 `stopped` 禁用。
- `CameraDetailPlayer` 根据 `previewRequested` 显式选择 `interactive` 或 `stopped`；测试单独覆盖
  `read-only`，防止它和停止预览再次混淆。
- 三种模式下的错误展示固定为：`interactive` 根据错误类型显示恢复按钮；`read-only` 只显示错误文字；
  `stopped` 优先显示“已停止”，不显示旧媒体错误或恢复按钮。

### Camera 类型和测试文件

- 在 Cameras API 类型边界统一导出 `CameraSummary`、`CameraSourceDetail` 和
  `CameraDefaultPreviewSource`，替换组件与测试中重复的索引访问类型。
- 类型整理只减少重复声明，不手写一份脱离 OpenAPI 的 Camera Schema，也不改变运行时代码。
- 按被测职责拆分过长的 `video-controls.test.tsx`：状态、loading、错误、操作栏模式，以及音量 Portal
  跨浏览器全屏重建的组合测试保留在原文件；纯音量 Popover 与 Slider 行为移入
  `volume-control.test.tsx`；纯显隐计时和浮层保持逻辑移入 `controls-visibility.test.tsx`。
- 浏览器全屏、网页全屏和两种模式互斥的底层行为继续由 `video-surface.test.tsx` 负责；不得为了按文件
  拆测试而删除操作栏与音量 Portal 的跨组件回归覆盖。
- 只有多个新测试文件确实重复同一套渲染装配时才增加同目录测试 helper；不得为单次调用创建抽象。

## 明确不做

- 不修改 `StreamSessionManager`、`useStreamSession`、MediaMTX WHEP reader、共享引用计数或重连实现。
- 不恢复视口相交比例、IntersectionObserver、Page Visibility、页面 hidden、防抖或冷却限制。
- 不改变搜索、翻页、切源、路由离开、组件卸载和 `whep_url=null` 时的 acquire/release 规则。
- 不把 Camera Card 和 Detail 合成一个包含大量布尔参数的播放器组件。
- 不把 Card Spinner 和 Detail 的“Spinner + 文字”抽成带 `compact` 开关的通用 loading overlay；两种展示
  保持各自明确实现。
- 不增加第二个视频 Context。`VideoSurfaceContext` 继续提供当前 video DOM 的 state、actions 和 meta。
- 除了为 Detail 的 Session 失败常驻提示增加“刷新当前流”按钮，不调整 Card、Detail、Badge、错误
  提示或操作栏的视觉样式，也不增加其他用户功能。
- 不在本任务中重排整个 `features/cameras/components/`；Camera 列表和详情目录分组留到组件继续增长时
  再处理。
- 不拆分或改写 `deriveVideoDisplayState` 的显式状态优先级为难以审查的配置表。

## 实施步骤

1. 建立 `features/video/display-state/`，迁移纯函数与测试，增加 `useVideoDisplayState` 及 Hook 测试，
   更新 Card 和 `VideoControls` 调用。
2. 增加只处理有效展示状态的统一 Badge，替换 Card 可预览分支与 Detail 的重复 Badge JSX；Card 的
   不可预览分支继续在 Camera 层渲染，并保留现有可访问文字和测试属性。
3. 为错误状态增加明确恢复方式，由 `VideoControls` 结合操作栏模式生成可选恢复动作；更新
   `PlaybackFeedback`，补齐 Session 失败的刷新入口和三种模式下的对应测试。
4. 用三种明确模式替换 `VideoControls` 的两个布尔参数，更新 `CameraDetailPlayer` 和测试，确认
   `read-only` 不暴露媒体恢复操作，停止预览不显示旧错误且不影响全屏退出能力。
5. 统一 Camera 派生类型并更新引用；本步骤不得改动生成的 `frontend/src/routeTree.gen.ts` 或 OpenAPI
   生成文件。
6. 按职责拆分操作栏测试，复用现有浏览器 mock，保留音量 Portal 与浏览器全屏的组合回归测试，保证
   测试只移动所有权而不降低行为覆盖。
7. 更新 Cameras 当前模块文档，并新增本任务的变更记录；只把 Session 失败刷新入口记录为用户可见
   修复，内部文件移动和类型别名不描述为新能力。

## 验证方式

```bash
# 仓库根目录
bash scripts/check-cameras-sensitive-data.sh
git diff --check

# frontend/
pnpm exec vitest run src/features/video/display-state
pnpm exec vitest run src/features/video/components/video-controls
pnpm exec vitest run src/features/cameras/components/camera-card-preview.test.tsx
pnpm exec vitest run src/features/cameras/components/camera-detail-player.test.tsx
pnpm test
pnpm lint
pnpm format:check
pnpm build
```

评审时额外检查 `frontend/src/features/video/` 不得反向引用 `features/cameras/`，Card 和 Detail 不得重新
出现相同的 `useVideoSurface` 展示状态映射或状态 Badge JSX。

## 完成标准

- Card 与 Detail 通过同一个 Hook 组合 Session 和当前 video DOM 状态，纯函数仍可独立测试。
- 两处播放器使用同一个状态 Badge 组件；不可预览输入不能和有效 Session 状态混搭。
- `VideoControls` 只能表达 `interactive/read-only/stopped` 三种有效模式。
- `interactive` 下播放受阻显示“继续播放”，画面超时和 Session 失败显示“刷新当前流”；
  `read-only` 下三类错误都只显示文字；`stopped` 不显示媒体错误或恢复按钮。
- Session 失败的刷新按钮调用现有 `session.reconnect`，不创建第二套重连实现。
- Card 仍只显示无文字 Spinner，不显示 Detail 错误恢复控件。
- Camera API 派生类型不在多个组件中重复声明。
- 操作栏测试按状态反馈、纯音量和纯显隐职责分开；原有全屏、音量 Portal、首帧和暂停行为仍有覆盖。
- Session Lease、页面 hidden、视口、搜索翻页、路由卸载和空 WHEP URL 的现有行为没有变化。
- 目标测试、Frontend 全量测试、Lint、格式检查、生产构建、敏感数据检查和差异检查全部通过。

## 与下一任务的衔接

08 完成后进入 [09｜更新 Camera 与切换默认源](../09-camera-update-default-source/README.md)。09 应使用本任务
整理后的 Camera 类型、状态 Hook 和 Badge，不得重新增加 Card 与 Detail 各自的状态映射；默认源更新
仍只通过最新列表和详情响应改变实际 Session 输入。
