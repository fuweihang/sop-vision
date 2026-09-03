# 任务 05b：确定性规则、WHEP 契约与 Session Fake

> 本任务必须在独立 Codex 会话中执行。05a 通过统一验证入口后才能开始。实施前先阅读
> [任务 5 总说明](./05-frontend-video.md)及其中列出的共同限制。

### 任务目标

把 Video 的纯计算、确定性 Session Manager 规则和 Frontend WHEP reader 边界迁入标准目录，并把
`FakeStreamSession` 从生产源码移到 Video 测试支持目录，同时保持 Cameras 和旧 render helper 可用。

### 当前上下文与前置条件

05a 已建立新旧路径并存的命令，并按 integration 登记 `frontend/tests/support/video/**`。当前候选是
Geometry、纯显示状态、`StreamSessionManager` 和 `WhepSession` 四组测试。`FakeStreamSession` 仍位于
`frontend/src/features/video/testing/fakes.ts`，被 Video、Cameras support 和 `src/test/render-router.tsx`
共同引用。

### 实施范围

- `frontend/tests/unit/video/` 中的 Geometry、纯显示状态和 `StreamSessionManager` 测试。
- `frontend/tests/contract/video/` 中的 `WhepSession` reader 边界测试。
- `frontend/tests/support/video/fake-stream-session.ts`。
- 现有 Fake 使用方的最小导入路径修改。
- 对应共置测试和失去用途的 `frontend/src/features/video/testing/`。

### 明确不做

不迁移 Controls、Surface、显示状态 Hook、Provider 或 `useStreamSession` 测试；不移动公共 Setup、
browser/media mocks 或 render-router；不增加 MediaMTX OpenAPI、HTTP Adapter、真实容器或真实浏览器
播放测试；不修改生产代码行为。

### 实施步骤

1. 逐项说明风险后迁移 `video-geometry.test.ts` 和 `video-display-state.test.ts`。合并或删除只能说明
   实现细节、没有独立风险的用例，不为目录完整补测试。
2. 将 `stream-session-manager.test.ts` 迁入 unit。虽然释放使用 microtask，但测试对象仍是无 React、
   无网络和无浏览器依赖的确定性引用规则，不放入 integration。
3. 将 `whep-session.test.ts` 迁入 contract，只保留以下边界：reader 延迟加载、configuration、Track
   组合、重试/失败状态、重连、关闭、迟到回调和错误脱敏。不重复 Backend MediaMTX 协议测试。
4. 将 `FakeStreamSession` 移到 `frontend/tests/support/video/fake-stream-session.ts`，保持直接、可控的
   Session 快照、重连和关闭行为，不为未来 Session 类型提前设计通用 Fake 框架。
5. 更新以下使用方导入：
   - 本任务迁移后的 Video 测试；
   - 尚待 05d 迁移的 Provider 与 Hook 共置测试；
   - `frontend/tests/support/cameras/render-with-stream-session.tsx`；
   - `frontend/src/test/render-router.tsx`。本任务只修改最后一个文件的 Fake 导入，不移动该 helper。
6. 删除四组已迁移的共置测试和原 Fake 文件；目录为空时删除失去用途的 testing 目录，不保留转发文件
   或第二份 Fake。

### 验证方式

只运行 `./scripts/verify-changed.sh`。Support 按 integration 触发后，Video 新旧测试和 Cameras 最终测试
都必须通过，不能手工缩小到 unit 或 contract。

### 完成标准与下一任务衔接

- Geometry、纯显示状态和 Manager 规则只位于 `unit/video`。
- WHEP reader 边界只位于 `contract/video`，且没有扩大到 Backend 或真实媒体职责。
- `FakeStreamSession` 只位于 `tests/support/video`，现有 Video、Cameras 和 render-router 使用方可运行。
- 对应共置测试和生产源码中的测试 Fake 已删除。

下一任务迁移 Controls、Surface 和显示状态 Hook 的组件行为。

## 导航

- [上一任务：05a Video 迁移期选择规则](./05a-video-transition-rules.md)
- [返回任务 5](./05-frontend-video.md)
- [下一任务：05c Video 组件行为](./05c-video-components.md)
