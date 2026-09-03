# 任务 5：Frontend Video 测试重构

> 本任务规模较大，已拆成 05a～05d 四个顺序任务。每个子任务必须在独立 Codex 会话中执行，
> 前一项通过统一验证入口后才能开始下一项，禁止并行修改同一工作区。

### 任务目标

重新评估视频控件、显示状态、Geometry、WHEP 和 Stream Session 测试，使纯规则、组件行为、外部
reader 接口和 React 会话生命周期分别进入正确层级，并删除 Video 共置测试及生产源码中的测试 Fake。

### 当前上下文与前置条件

任务 4 已完成，Cameras 测试和命令已经使用标准目录。Video 当前有 11 个共置测试文件，约 1400 行，
分布在 `frontend/src/features/video/` 的 controls、surface、display-state、geometry、mediamtx 和
stream-session 中。`frontend-video` 当前仍运行旧目录，并通过 `impacts` 触发 Cameras 最终命令。

现有 `FakeStreamSession` 位于 `frontend/src/features/video/testing/fakes.ts`，除 Video 测试外，还被
`frontend/tests/support/cameras/render-with-stream-session.tsx` 和任务 6 才会迁移的
`frontend/src/test/render-router.tsx` 使用。公共 Setup、browser/media mocks 和 render-router 本身仍由
任务 6 负责，本任务只更新它们对 Video Fake 的导入。

开始每个子任务前，都要重新读取当前版本的 `AGENTS.md`、总计划、`test-policy`、Frontend 参考、
`test-impact.json` 和该子任务方案。默认不修改生产代码行为；发现生产问题时记录，不借测试迁移修改
实现。

### 已确定的归属

- Geometry、纯显示状态转换和 `StreamSessionManager` 的引用计数、URL 替换、microtask 释放规则进入
  `frontend/tests/unit/video/`。
- Controls、Volume、Visibility、Surface 和 `useVideoDisplayState` 的用户可见行为进入
  `frontend/tests/component/video/`。
- `WhepSession` 与固定版本 MediaMTX reader 的配置、回调、Track、重试、关闭和脱敏边界进入
  `frontend/tests/contract/video/`。
- `StreamSessionProvider`、`useStreamSession`、Strict Mode 和 React 生命周期协作进入
  `frontend/tests/integration/video/`。
- `FakeStreamSession` 进入 `frontend/tests/support/video/fake-stream-session.ts`。该 Fake 同时影响 Video
  integration 和 Cameras，因此 `frontend/tests/support/video/**` 在 `frontend-video.source` 中按
  integration 登记，并继续通过既有 `impacts: ["frontend-cameras"]` 验证 Cameras。
- `pnpm vendor:check` 是固定 reader 副本的确定性校验，加入 Video integration 最终命令。
  `whep:test-source` 需要真实媒体环境，只保留为手工验收辅助工具，不加入统一验证命令。

### WHEP 与 MediaMTX 边界

本任务只验证 Frontend `WhepSession` 与仓库固定 reader 接口的兼容性，不重复以下职责：

- `contracts/mediamtx-openapi.json` 的管理接口协议由 Backend Stream Gateway 测试负责。
- MediaMTX HTTP Adapter、真实容器和 WHEP 真实浏览器播放不在本任务内。
- Cameras 的 `whep_url` 投影、选择和页面行为继续由 Cameras 测试负责。
- 跨端协议是否重复或遗漏由任务 7 做最终检查。

### 所有子任务共同限制

1. 四个子任务必须严格按 05a～05d 串行执行。
2. 每个阶段先说明测试要防止的缺陷，再决定保留、合并、重写或删除，不按文件机械搬运。
3. 05a～05c 使用新旧路径并存的迁移期命令；已迁移测试立即删除旧副本。
4. 不移动 `frontend/src/test/setup.ts`、browser/media mocks 或 render-router；任务 5 只允许修改
   render-router 的 Fake 导入。
5. 使用可控事件、microtask 或 fake timers 驱动异步状态，不使用休眠或真实媒体环境。
6. 不新增浏览器 E2E、视觉回归、截图或快照测试，不修改生产代码行为。
7. 每个阶段交付前只运行 `./scripts/verify-changed.sh`；只有 05d 可以删除 Video 旧命令并切换最终命令。

### 子任务执行顺序

1. [05a：Video 迁移期选择规则](./05a-video-transition-rules.md)
2. [05b：确定性规则、WHEP 契约与 Session Fake](./05b-video-rules-contract-and-support.md)
3. [05c：Video 组件行为](./05c-video-components.md)
4. [05d：Stream Session 集成与迁移收尾](./05d-video-integration-and-finalization.md)

### 任务 5 完成标准与下一任务衔接

四个子任务全部通过后，Video 测试只位于 unit、component、contract 和 integration 标准目录，
`FakeStreamSession` 位于 Video test support，固定 reader 校验由 integration 命令执行。公共 Setup、
browser/media mocks 和 render-router 仍保留原位置，供任务 6 一次性迁移。Video 及其影响的 Cameras
最终命令必须全部通过。

## 导航

- [上一任务：04h Cameras 迁移收尾](./04h-cameras-finalization.md)
- [返回总计划](./README.md)
- [首先执行：05a Video 迁移期选择规则](./05a-video-transition-rules.md)
- [任务 5 完成后：Frontend Shared 与 App Shell](./06-frontend-shared-app-shell.md)
