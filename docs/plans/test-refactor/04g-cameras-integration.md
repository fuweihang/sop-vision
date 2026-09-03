# 任务 04g：React Query、MSW 与路由流程

> 本任务必须在独立 Codex 会话中执行。04f 通过统一验证入口后才能开始。实施前先阅读
> [任务 4 总说明](./04-frontend-cameras.md)及其中列出的共同限制。

### 任务目标

迁移 Cameras 剩余的 React Query、MSW Handler、列表路由和详情路由测试，完成业务测试文件的实际
搬迁，为 04h 最终切换命令准备完整新目录。

### 当前上下文与前置条件

04b～04f 已迁移纯规则、Contract、组件和写入流程。剩余测试覆盖 Query 缓存与重试、MSW 六个
operation、分页/搜索、路由历史、错误恢复、Breadcrumb 以及 Card/Detail 路由切换时的 Session 复用。
共享 Router/browser/media helper 仍由任务 6 负责，本任务继续从旧位置复用。

### 实施范围

- `frontend/tests/integration/cameras/` 中 Query、MSW、列表路由和详情路由测试。
- `src/mocks/cameras/scenarios.test.ts`，以及仍未迁移的 Cameras query/route 共置测试。
- 04a 建立的过渡命令；只有发现路径选择遗漏时才最小修改 Test Infrastructure 回归测试。

### 明确不做

不移动运行时 `fixtures.ts`、`scenarios.ts`、browser Mock 和 enable-api-mocking，不迁移 App Shell 的
通用路由测试，不修改生产查询、路由或 Session 行为。

### 实施步骤

1. 迁移 Query Options 的缓存身份、可见性、重试、回收和注入 Client 行为；合并已由 unit query key
   测试覆盖的重复断言。
2. 迁移 MSW Scenario 测试，验证请求/响应、分页、状态更新、错误格式、敏感字段排除和未处理请求失败。
3. 迁移列表路由的 search、分页历史、加载/刷新失败、Card 摘要和 Session 释放流程。
4. 迁移详情路由的直接 URL、Breadcrumb、焦点、Not Found、错误和后台刷新流程。
5. 删除所有剩余 Cameras 共置测试；使用 `rg` 确认没有遗漏 `.test.ts(x)`，但暂不删除过渡命令。

### 验证方式

只运行 `./scripts/verify-changed.sh`，确认 Cameras 全部新目录、API Contract、Shell 过渡测试与 Test
Infrastructure 均通过。

### 完成标准与下一任务衔接

- Cameras 业务测试不再与源码共置。
- `tests/integration/cameras` 覆盖 Query、MSW 和路由流程，没有重复 unit/component 行为。
- 运行时开发 Mock 与全局测试辅助代码仍保持可用。

下一任务只做影响规则、最终命令和遗留路径收尾，不再重写测试设计。

## 导航

- [上一任务：04f 创建、编辑与默认源写入流程](./04f-cameras-write-flows.md)
- [返回任务 4](./04-frontend-cameras.md)
- [下一任务：04h Cameras 迁移收尾](./04h-cameras-finalization.md)
