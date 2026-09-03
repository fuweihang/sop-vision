# 任务 04f：创建、编辑与默认源写入流程

> 本任务必须在独立 Codex 会话中执行。04e 通过统一验证入口后才能开始。实施前先阅读
> [任务 4 总说明](./04-frontend-cameras.md)及其中列出的共同限制。

### 任务目标

迁移 Camera 创建、编辑和默认预览源更新流程，保留提交锁定、服务端错误、未知结果重读、焦点恢复
和缓存刷新等用户可见行为。

### 当前上下文与前置条件

三个现有测试文件使用 Router render helper、React Query 和 MSW。虽然组件入口是 Dialog 或局部控件，
需要真实模块协作与网络 Mock 的完整流程属于 `integration/cameras`；能在不削弱风险覆盖的情况下完全
隔离网络的局部交互才留在 component。

### 实施范围

- `frontend/tests/integration/cameras/` 中创建、编辑和默认源写入流程。
- 确有独立价值的 `frontend/tests/component/cameras/` 局部 Dialog 行为。
- 对应共置测试删除和重复 render setup 合并；继续使用 04a 建立的新旧目录过渡命令。

### 明确不做

不修改表单或 API 生产实现，不重复 04b 的 Schema/错误映射规则，不迁移列表和详情路由，不移动共享
Router render helper、MSW Node Setup 或全局 Setup。

### 实施步骤

1. 按是否需要 Router、Query Client 和 MSW，把局部 Dialog 行为与完整写入流程放入最低有效层级。
2. 保留 Source 添加、排序、删除、默认选择、提交载荷、提交锁定、422 聚焦和表单级 Alert 行为。
3. 保留编辑草稿、离开确认、未知结果重读和失败后重试行为；删除与 04b 错误映射重复的纯函数断言。
4. 保留默认源更新的旧值保持、重复提交阻止和重新读取确认行为。
5. 删除共置旧文件，继续复用任务 6 尚未迁移的全局辅助代码；旧目录过滤条件留到 04h 统一删除。

### 验证方式

只运行 `./scripts/verify-changed.sh`，确认 Cameras component/integration、API Contract 与剩余路由测试
均通过。

### 完成标准与下一任务衔接

- 三类写入流程位于正确的新目录。
- 用户操作和网络结果由 MSW 边界验证，不断言 Mutation 内部调用次数。
- 表单纯规则没有在 Integration 中重复维护。

下一任务处理 Query、MSW 场景及列表/详情路由。

## 导航

- [上一任务：04e 视频预览组件](./04e-cameras-preview-components.md)
- [返回任务 4](./04-frontend-cameras.md)
- [下一任务：04g React Query、MSW 与路由流程](./04g-cameras-integration.md)
