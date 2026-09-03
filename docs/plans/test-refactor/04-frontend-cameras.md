# 任务 4：Frontend Cameras 测试重构

> 本任务在独立 Codex 会话中执行。实施前先阅读[总计划与通用要求](./README.md)，完成并通过统一验证入口后再进入下一任务。

### 任务目标

重构 Cameras API Client、查询、表单、组件、页面和 Mock 场景测试，按用户可见行为和网络边界
选择层级。

### 当前上下文与前置条件

现有测试与源码共置在 `frontend/src/features/cameras/`、`frontend/src/mocks/` 和相关路由目录，
新目录为 `frontend/tests/<layer>/cameras/`。Cameras 没有继续影响其他 Frontend 测试模块，适合先
迁移。全局 Setup 在任务 6 最终迁移；本任务不得复制一套长期并存的全局 Setup。

### 实施范围

- API、query keys、错误映射、表单、分页和预览选择测试。
- Cameras 组件、对话框、详情、列表和路由测试。
- Cameras mocks、Fixture、Handler、Fake 和 Builder。
- Cameras 对应的 unit、component、contract 和 integration 目录。

### 明确不做

不处理 Video、App Shell、Shared 或生产代码，不新增浏览器 E2E。

### 实施步骤

1. 将 Schema、错误映射、query key、分页和选择规则迁移到 `unit/cameras`。
2. 将可见状态、交互和无障碍行为迁移到 `component/cameras`。
3. 将生成类型、API 载荷和错误格式兼容性迁移到 `contract/cameras`。
4. 将路由、React Query、MSW 请求和跨组件流程迁移到 `integration/cameras`。
5. 合并重复渲染工具，删除共置测试及无价值断言。

### 验证方式

运行 `./scripts/verify-changed.sh`，不要用 Vitest 文件过滤器代替统一入口。

### 完成标准与下一任务衔接

Cameras 测试全部进入标准目录；组件测试从用户视角断言，不依赖内部状态、CSS 类名或调用次数；
统一验证入口通过。Video 会影响 Cameras，因此下一任务开始前 Cameras 的各级命令必须可运行。

## 导航

- [返回总计划](./README.md)
- [下一任务](./05-frontend-video.md)
