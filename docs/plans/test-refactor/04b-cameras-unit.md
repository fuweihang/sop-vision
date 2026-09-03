# 任务 04b：Cameras Unit 测试

> 本任务必须在独立 Codex 会话中执行。04a 通过统一验证入口后才能开始。实施前先阅读
> [任务 4 总说明](./04-frontend-cameras.md)及其中列出的共同限制。

### 任务目标

把 Cameras 的确定性规则迁入 `frontend/tests/unit/cameras/`，清理重复和无法说明实际风险的用例，
同时保持浏览器开发 Mock 可用。

### 当前上下文与前置条件

04a 已建立新旧路径并存的过渡命令。Unit 候选包括 query key、表单 Schema/转换、错误映射、列表
page size、预览选择以及 Fixture Builder。`src/mocks/cameras/fixtures.ts` 被开发 Mock 使用，不是纯测试
辅助文件。

### 实施范围

- `frontend/tests/unit/cameras/`。
- 现有 Cameras API、forms、components 和 `src/mocks/cameras` 中只验证纯规则的测试。
- 04a 已建立的过渡命令；只有发现新 unit 目录未被正确选择时才修改 Test Infrastructure 回归测试。

### 明确不做

不迁移 API 请求边界、React Query 生命周期、DOM 交互、MSW Handler、路由或异步流程；不移动
`fixtures.ts`、`scenarios.ts` 和全局辅助代码。

### 实施步骤

1. 迁移 `camera-query-keys`、表单 Schema/转换、创建/编辑/默认源错误映射、page size 和预览选择规则。
2. 迁移 Fixture Builder 测试；保留 Builder 运行时代码原路径，测试通过 `@/mocks/...` 导入它。
3. 将只因旧文件布局分散而重复的规则用例合并到已有主题文件，不为目录完整性创建空测试。
4. 删除已迁移的共置测试；保留 04a 的旧目录过滤条件，让同目录内尚未迁移的测试继续执行。

### 验证方式

只运行 `./scripts/verify-changed.sh`，确认 Test Infrastructure 与 Cameras 过渡命令都通过。

### 完成标准与下一任务衔接

- 所有确定性 Cameras 规则位于 `tests/unit/cameras`。
- 对应共置测试已删除，运行时 Fixture 和开发 Mock 行为未改变。
- 后续任务可以复用已验证的 Fixture Builder，不重复测试相同派生规则。

下一任务处理 Cameras API Client 和公共生成物检查。

## 导航

- [上一任务：04a Frontend 迁移期选择规则](./04a-frontend-transition-rules.md)
- [返回任务 4](./04-frontend-cameras.md)
- [下一任务：04c API Client 与公共生成物检查](./04c-cameras-contracts.md)
