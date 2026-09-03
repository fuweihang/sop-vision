# 任务 5：Frontend Video 测试重构

> 本任务在独立 Codex 会话中执行。实施前先阅读[总计划与通用要求](./README.md)，完成并通过统一验证入口后再进入下一任务。

### 任务目标

重构视频控件、显示状态、Geometry、WHEP 和 Stream Session 测试，明确组件行为、会话状态和外部
协议边界。

### 当前上下文与前置条件

现有测试与源码共置在 `frontend/src/features/video/`，新目录为
`frontend/tests/<layer>/video/`。`frontend-video` 会影响 `frontend-cameras`，因此任务 4 必须完成。

### 实施范围

- Video controls、surface、display state、geometry、WHEP 和 stream session 测试。
- Video 对应的 unit、component、contract 和 integration 目录。
- Video 专用 Fake 和渲染辅助代码。

### 明确不做

不建立视觉回归、截图测试或真实流媒体 E2E，不处理 App Shell、Shared 或生产代码。

### 实施步骤

1. 将 Geometry、显示状态转换和确定性会话规则迁移到 `unit/video`。
2. 将控件、音量、可见状态和 Surface 交互迁移到 `component/video`。
3. 将 WHEP、MediaMTX 载荷和协议兼容性迁移到 `contract/video`。
4. 将 Provider、Manager、Hook、异步会话和跨组件流程迁移到 `integration/video`。
5. 使用可控事件或 Fake 驱动异步状态，不使用休眠等待，清理旧共置测试。

### 验证方式

运行 `./scripts/verify-changed.sh`，确认 Video 及其影响的 Cameras 测试均通过。

### 完成标准与下一任务衔接

Video 测试全部进入标准目录，异步测试不依赖真实时间或媒体环境，WHEP 契约与会话行为没有重复。
Shared 会触发 Shell、Cameras 和 Video，任务 6 开始前 Video 新目录必须可运行。

## 导航

- [返回总计划](./README.md)
- [下一任务](./06-frontend-shared-app-shell.md)
