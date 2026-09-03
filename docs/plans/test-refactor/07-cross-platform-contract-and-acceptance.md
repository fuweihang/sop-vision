# 任务 7：跨端契约与迁移验收

> 本任务在独立 Codex 会话中执行。实施前先阅读[总计划与通用要求](./README.md)，完成并通过统一验证入口后结束本轮测试重构。

### 任务目标

处理跨 Backend/Frontend 的 API Contract、敏感数据和 MediaMTX 兼容性检查，并确认所有测试都能
被 `test-impact.json` 唯一识别和正确选择。

### 当前上下文与前置条件

前六个任务已经完成并分别通过。Backend 和 Frontend 业务测试已经使用标准目录。现有跨端检查
涉及 OpenAPI、生成类型、Cameras 敏感数据、MediaMTX 协议文件和检查脚本。

### 实施范围

- `backend/tests/contract/api_contract/`
- `frontend/tests/contract/api_contract/`
- Cameras Contract/Sensitive Data 测试的最终归属。
- OpenAPI、生成类型和 MediaMTX 协议相关测试的选择结果。
- 旧测试路径、重复辅助代码和 `test-impact.json` 实际匹配结果。
- 仅在证明规则有误时，最小修改测试脚本或 `test-impact.json`，并补充
  `tests/unit/test_infrastructure/` 回归测试。

### 明确不做

不新增 E2E、视觉回归或 CI 流程，不借最终验收重写已通过的模块测试，不修改 Git/PR skill，也不
把测试流程加入这些 skill。

### 实施步骤

1. 确认公共 HTTP Schema、生成类型和跨端载荷检查归入 `api-contract`，不重复业务行为测试。
2. 确认敏感数据测试覆盖必要的跨层泄漏风险，并使用正确层级。
3. 检查 MediaMTX 协议测试在 Stream Gateway 与 Video 之间没有重复或遗漏。
4. 使用 `rg` 查找仍位于旧 Backend 目录、Frontend 源码旁或 `frontend/src/test/` 的测试。
5. 检查所有新路径都被唯一模块识别，生产路径变化能选择预期的最低测试范围。
6. 如有实际遗漏，最小修改影响规则或脚本，并增加测试工具回归测试。

### 验证方式

运行 `./scripts/verify-changed.sh`。失败时只检索临时日志中的关键错误，不通过手工缩小测试范围
掩盖选择规则问题。

### 完成标准与后续处理

- 旧目录和源码旁不再存在业务测试。
- 所有测试都有唯一的平台、层级和模块归属。
- Cross API、敏感数据和 MediaMTX 测试各自覆盖明确风险，没有明显重复。
- 未登记生产源码会导致检查失败；已登记源码只选择必要模块并按规模升级。
- Git、PR、Test 三类 skill 保持独立，统一验证入口通过。

完成后按 `docs/plans/README.md` 的规则补充必要的模块文档和变更记录，再移除本计划。

## 导航

- [返回总计划](./README.md)
