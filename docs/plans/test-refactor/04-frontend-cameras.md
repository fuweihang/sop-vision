# 任务 4：Frontend Cameras 测试重构

> 本任务规模较大，已拆成 04a～04h 八个顺序任务。每个子任务必须在独立 Codex 会话中执行，
> 前一项通过统一验证入口后才能开始下一项，禁止并行修改同一工作区。

### 任务目标

重新评估 Cameras 的纯规则、API Client、组件、写入流程、React Query、MSW 和路由测试，使每个测试
只有一个层级和模块归属，并删除 Cameras 共置测试。生产环境使用的开发 Mock 继续留在 `src/mocks/`，
不把可运行源码误迁入测试目录。

### 当前上下文与前置条件

任务 3 已完成，Backend 测试已经使用标准目录。Frontend Cameras 当前有 27 个相关测试文件，约
4200 行，分布在 `frontend/src/features/cameras/`、`frontend/src/mocks/cameras/`、Cameras 路由目录和
`frontend/src/test/`，同时依赖全局 Setup、Router render helper、浏览器媒体 Mock 和 Video Session
Fake，不能在一个会话中可靠完成。

当前 `test-impact.json` 仍让 `frontend-cameras` 运行旧共置测试，这是任务 4 的正确起点；但尚未迁移
的 `frontend-shared`、`frontend-shell` 和 `frontend-video` 已提前指向不存在的新目录。04a 必须先恢复
这些模块的过渡命令，之后才能移动会触发它们的 Cameras 路由测试或 Vitest 配置。

开始每个子任务前，都要重新读取当前版本的 `AGENTS.md`、总计划、`test-policy`、Frontend 参考、
`test-impact.json` 和该子任务方案。默认不修改生产代码行为；发现生产问题时记录，不借测试迁移修改
实现。

### 已确定的归属

- Query key、表单 Schema/转换、错误映射、分页和预览选择等确定性规则进入
  `frontend/tests/unit/cameras/`。
- 单个组件或小型组件组合的可见状态、交互和无障碍行为进入
  `frontend/tests/component/cameras/`。
- Cameras API Client 的方法、路径、参数、请求体和响应边界进入
  `frontend/tests/contract/cameras/`。
- OpenAPI、生成类型、敏感字段哨兵和跨端生成物一致性直接进入
  `frontend/tests/contract/api_contract/`，不在 `contract/cameras` 中保留副本。
- React Query、MSW 请求、路由、异步刷新和跨组件流程进入
  `frontend/tests/integration/cameras/`。
- `frontend/src/mocks/cameras/fixtures.ts` 和 `scenarios.ts` 被浏览器开发 Mock 使用，继续作为运行时代码
  留在 `src/mocks/`；只迁移它们的测试。
- Cameras 专用渲染辅助代码可进入 `frontend/tests/support/cameras/`。全局 Setup、Router render
  helper、browser/media mocks 和 MSW Node Setup 由任务 6 统一迁移，本任务只复用，不复制第二套。
- Cameras 路由源码同时属于 `frontend-shell` 和 `frontend-cameras` 的影响范围；修改这些文件应执行
  Shell 与 Cameras 测试，但不新增 Cameras 对其他 Frontend 模块的 `impacts` 关系。

### 所有子任务共同限制

1. 八个子任务必须严格按 04a～04h 串行执行。
2. 每个阶段先说明测试要防止的缺陷，再决定保留、合并、重写或删除，不按文件机械搬运。
3. 04b～04g 处于过渡期。每个阶段都要让 `frontend-cameras` 命令同时覆盖已经迁移的新目录与仍有
   测试的旧目录；已迁移测试立即删除旧副本。
4. 不移动 `frontend/src/mocks/` 中供 `VITE_API_MOCK_SCENARIO` 使用的运行时代码。
5. 不在本任务迁移全局 Setup 和共享 Router/browser/media helper，不复制长期并存的公共辅助代码。
6. 不手工编辑 `contracts/openapi.json`、`frontend/src/generated/openapi.ts` 或
   `frontend/src/routeTree.gen.ts`。
7. 不新增浏览器 E2E、视觉回归或截图测试，不修改生产代码行为。
8. 每个阶段交付前只运行 `./scripts/verify-changed.sh`；只有 04h 可以删除全部 Cameras 旧命令并切换
   到最终三档命令。

### 子任务执行顺序

1. [04a：Frontend 迁移期选择规则](./04a-frontend-transition-rules.md)
2. [04b：Cameras Unit 测试](./04b-cameras-unit.md)
3. [04c：API Client 与公共生成物检查](./04c-cameras-contracts.md)
4. [04d：基础组件行为](./04d-cameras-components.md)
5. [04e：视频预览组件](./04e-cameras-preview-components.md)
6. [04f：创建、编辑与默认源写入流程](./04f-cameras-write-flows.md)
7. [04g：React Query、MSW 与路由流程](./04g-cameras-integration.md)
8. [04h：Cameras 迁移收尾](./04h-cameras-finalization.md)

### 任务 4 完成标准与下一任务衔接

八个子任务全部通过后，Cameras 测试只位于标准目录，公共生成物检查直接归 `api_contract`，运行时
开发 Mock 仍可用，Cameras 专用辅助代码位于 `tests/support/cameras`，共置测试和过渡命令已删除。
此时 `frontend-video` 对 `frontend-cameras` 的影响关系必须使用 Cameras 最终命令，之后才能进入
任务 5。

## 导航

- [返回总计划](./README.md)
- [首先执行：04a Frontend 迁移期选择规则](./04a-frontend-transition-rules.md)
- [任务 4 完成后：Frontend Video](./05-frontend-video.md)
