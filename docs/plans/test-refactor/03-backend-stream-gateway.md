# 任务 3：Backend Stream Gateway 测试重构

> 本任务在独立 Codex 会话中执行。实施前先阅读[总计划与通用要求](./README.md)，完成并通过统一验证入口后再进入下一任务。

### 任务目标

重构投影、URL、端口、MediaMTX 适配和协议测试，区分本地规则、模块协作与真实外部边界。

### 当前上下文与前置条件

现有测试主要位于 `backend/tests/modules/stream_gateway/`，新目录为
`backend/tests/<layer>/stream_gateway/`。`backend-stream-gateway` 会影响 `backend-cameras`，因此
任务 2 必须已经完成并通过。本任务完成时移除最后一组 Backend 旧目录过渡命令。

### 实施范围

- ports、projection、urls、MediaMTX adapter 和 OpenAPI/协议测试。
- `backend/tests/unit/stream_gateway/`
- `backend/tests/module/stream_gateway/`
- `backend/tests/contract/stream_gateway/`
- `backend/tests/integration/stream_gateway/`
- Stream Gateway 专用测试辅助代码。
- `backend-stream-gateway` 对应的新目录测试命令和选择器回归测试。

### 明确不做

不搭建真实 MediaMTX E2E 环境，不再次处理 Backend Core 或 Cameras，不处理 Frontend Video，不修改
生产行为。

### 实施步骤

1. 将纯 URI、端口和投影规则迁移到 `unit/stream_gateway`。
2. 将模块内端口与服务协作迁移到 `module/stream_gateway`。
3. 将 MediaMTX/OpenAPI 兼容性检查迁移到 `contract/stream_gateway`。
4. 只有需要真实 HTTP、文件或外部适配边界的测试才进入 `integration/stream_gateway`。
5. 删除重复健康检查和只验证内部调用次数的测试，清理旧目录。
6. 把 `backend-stream-gateway` 验证命令从旧目录切换到四个新目录，更新选择器回归测试，并确认
   Backend 不再依赖旧测试目录过渡命令。

### 验证方式

运行 `./scripts/verify-changed.sh`，确认 Stream Gateway 及其影响的 Cameras 测试均通过。

### 完成标准与下一任务衔接

测试全部位于标准目录，Fake/契约测试与真实集成边界区分清楚，Backend 的测试命令不再引用旧测试
目录，Core、Cameras 和 Stream Gateway 均通过。后续跨端验收以三个任务的结果为后端基准。

## 导航

- [返回总计划](./README.md)
- [下一任务](./04-frontend-cameras.md)
