# 任务 04d：基础组件行为

> 本任务必须在独立 Codex 会话中执行。04c 通过统一验证入口后才能开始。实施前先阅读
> [任务 4 总说明](./04-frontend-cameras.md)及其中列出的共同限制。

### 任务目标

迁移不依赖完整路由、写请求或视频 Session 的 Cameras UI 行为，使断言只观察用户可见结果和
无障碍状态。

### 当前上下文与前置条件

04b 已迁移组件目录中的纯规则测试。本任务处理连接信息、Source 表格、搜索输入和详情操作等局部
组件；需要网络、路由或视频 Session 的场景留给后续任务。

### 实施范围

- `frontend/tests/component/cameras/`。
- Camera connection information、list search、sources、detail actions 等局部组件测试。
- 对应的共置测试删除；继续使用 04a 建立的新旧目录过渡命令。

### 明确不做

不处理 Card/Detail 播放器、创建/编辑 Dialog、默认源写入、React Query、MSW 或路由页面；不迁移
全局 render helper。

### 实施步骤

1. 逐个确认测试保护的可见字段、交互、焦点、按钮状态或无障碍名称。
2. 使用 Testing Library 的角色、名称和可见内容查询，移除 CSS 类名、内部状态或子组件调用次数断言。
3. 合并只重复静态渲染的场景，保留能防止字段泄漏、操作不可达或响应式交互退化的测试。
4. 删除已迁移共置文件；保留旧目录过滤条件，让该目录内尚未迁移的测试继续执行。

### 验证方式

只运行 `./scripts/verify-changed.sh`，确认 Cameras unit、contract、component 新目录和剩余共置测试均
通过。

### 完成标准与下一任务衔接

- 基础组件测试位于 `tests/component/cameras`。
- 断言不依赖内部实现细节。
- 视频 Session、写入和路由用例仍由过渡命令完整执行。

下一任务处理 Camera Card 与 Detail 播放组件。

## 导航

- [上一任务：04c API Client 与公共生成物检查](./04c-cameras-contracts.md)
- [返回任务 4](./04-frontend-cameras.md)
- [下一任务：04e 视频预览组件](./04e-cameras-preview-components.md)
