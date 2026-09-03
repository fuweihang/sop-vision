# 任务 05c：Video 组件行为

> 本任务必须在独立 Codex 会话中执行。05b 通过统一验证入口后才能开始。实施前先阅读
> [任务 5 总说明](./05-frontend-video.md)及其中列出的共同限制。

### 任务目标

把 Video Controls、Volume、Visibility、Surface 和显示状态 Hook 的用户可见行为迁入
`frontend/tests/component/video/`，清理重复或只依赖内部实现的断言。

### 当前上下文与前置条件

05b 已迁移纯规则、WHEP 契约和 Session Fake。当前五组组件测试仍与源码共置，其中 Controls 和
Surface 覆盖媒体事件、首帧、播放意图、全屏、错误提示和恢复操作，并临时依赖
`frontend/src/test/media-browser-mocks.ts`。05a 的迁移期命令会同时执行新目录与剩余旧测试。

### 实施范围

- `frontend/tests/component/video/`。
- `controls-visibility.test.tsx`、`volume-control.test.tsx`、`video-controls.test.tsx`、
  `video-surface.test.tsx` 和 `use-video-display-state.test.tsx`。
- 本阶段需要的 Video 专用局部渲染或事件辅助代码；只有多个 Video 测试确实复用时才放入
  `frontend/tests/support/video/`。

### 明确不做

不迁移 Provider 或 `useStreamSession`；不移动、复制或重写公共 Setup、browser/media mocks、
render-router 或 Vitest 配置；不增加截图、快照、真实媒体播放或生产代码修改。

### 实施步骤

1. 对每个用例先说明要防止的用户可见缺陷，删除只验证 Hook 调用、内部状态、CSS 类名或重复状态
   组合的断言。
2. 迁移 Controls、Volume 和 Visibility，保留播放/暂停、刷新、音量恢复、浮层期间可见性和可访问
   操作等实际行为。
3. 迁移 Surface，保留 `srcObject` 生命周期、原生媒体/全屏事件、换流播放意图和只接受当前 Stream
   首帧回调等行为。
4. 将 `useVideoDisplayState` 与 `VideoSurface` 的组合测试放入 component；纯状态优先级已经由 05b 的
   unit 测试负责，不在此重复组合表。
5. 继续从原路径导入 `media-browser-mocks`。定时行为使用 fake timers，媒体行为使用可控事件，不使用
   真实等待或休眠。
6. 删除五组已迁移的共置测试，保留 05a 建立的旧目录过滤条件供 05d 使用。

### 验证方式

只运行 `./scripts/verify-changed.sh`，确认 Video 迁移期命令和受影响的 Cameras 最终测试通过。

### 完成标准与下一任务衔接

- Controls、Volume、Visibility、Surface 和显示状态 Hook 测试只位于 `component/video`。
- 测试从用户可见行为查询和断言，没有休眠、真实媒体或新增快照。
- 公共媒体 Mock 仍保留原位置且只有一份，等待任务 6 迁移。

下一任务迁移 React Session 生命周期测试，并把 Video 切换到最终命令。

## 导航

- [上一任务：05b 确定性规则、WHEP 契约与 Session Fake](./05b-video-rules-contract-and-support.md)
- [返回任务 5](./05-frontend-video.md)
- [下一任务：05d Stream Session 集成与迁移收尾](./05d-video-integration-and-finalization.md)
