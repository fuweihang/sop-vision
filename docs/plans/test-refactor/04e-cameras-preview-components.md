# 任务 04e：视频预览组件

> 本任务必须在独立 Codex 会话中执行。04d 通过统一验证入口后才能开始。实施前先阅读
> [任务 4 总说明](./04-frontend-cameras.md)及其中列出的共同限制。

### 任务目标

迁移 Camera Card、Detail Player 和 Detail View 的播放意图、Lease、切源和可见状态测试，并把
Cameras 专用 Session 渲染工具移出生产源码目录。

### 当前上下文与前置条件

现有三个组件测试通过 `features/cameras/testing/render-with-stream-session.tsx` 注入可控
`FakeStreamSession`。该 helper 只服务 Cameras 测试，可以迁入 Cameras support；它当前引用的 Video
Fake 会在任务 5 迁移，届时需根据本任务留下的衔接信息更新导入。

### 实施范围

- `frontend/tests/component/cameras/` 中 Card Preview、Detail Player、Detail View 测试。
- `frontend/tests/support/cameras/render-with-stream-session.tsx`。
- 对应共置测试和旧 Cameras testing helper；继续使用 04a 建立的新旧目录过渡命令。

### 明确不做

不迁移或重写 Video 模块测试和 Fake，不建立真实媒体环境，不处理路由级 Card/Detail 切换，不移动
全局 browser/media mocks。

### 实施步骤

1. 迁移 Cameras 专用 render helper，保持 Query Client、Tooltip 与 Stream Session Provider 的最小包装。
2. 迁移无 URL 占位、加载超时、暂停/恢复、切源、隐藏页面、Strict Mode、共享 Session 和卸载释放行为。
3. 使用 Fake 事件和 Vitest 可控时间推进异步状态，不使用真实休眠或媒体设备。
4. 删除旧测试与旧 Cameras testing helper，并更新全部导入；旧目录过滤条件留到 04h 统一删除。
5. 在完成说明中记录对 Video `FakeStreamSession` 旧路径的依赖，供任务 5 修正。

### 验证方式

只运行 `./scripts/verify-changed.sh`，确认 Cameras component 测试和剩余路由集成测试均通过。

### 完成标准与下一任务衔接

- 三个视频预览组件测试位于 `tests/component/cameras`。
- Cameras 专用 helper 位于 `tests/support/cameras`，没有复制全局 Setup。
- 测试不依赖真实时间、真实 MediaStream 或实际 MediaMTX。

下一任务处理创建、编辑和默认预览源写入流程。

## 导航

- [上一任务：04d 基础组件行为](./04d-cameras-components.md)
- [返回任务 4](./04-frontend-cameras.md)
- [下一任务：04f 创建、编辑与默认源写入流程](./04f-cameras-write-flows.md)
