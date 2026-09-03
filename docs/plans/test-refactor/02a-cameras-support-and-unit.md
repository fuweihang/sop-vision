# 任务 02a：Cameras 测试辅助代码与 Unit 测试

> 本任务必须在独立 Codex 会话中执行，是 Cameras 七个子任务中的第一项。实施前先阅读
> [任务 2 总说明](./02-backend-cameras.md)及其中列出的共同限制。

### 任务目标

建立 Cameras 专用测试辅助目录，迁移纯领域规则、值对象、媒体差异和状态计算测试，为后续模块测试
提供稳定的 Builder 与 Fake。

### 当前上下文与前置条件

任务 1 已完成并通过。现有 `builders.py`、`constants.py`、`fakes.py` 和
`repository_contract.py` 位于 legacy 业务测试目录；领域测试与应用、数据库测试共用这些辅助代码。
新位置为 `backend/tests/support/cameras/` 和 `backend/tests/unit/cameras/`。

### 实施范围

- 重新评估并迁移 `test_domain_aggregate.py`、`test_domain_values.py`、`test_media.py`、
  `test_camera_status.py` 中的确定性规则。
- 将 Cameras 专用 Builder、Fake、常量和 Repository 共享检查迁入
  `backend/tests/support/cameras/`。
- 更新所有尚留在 legacy 的 Cameras 测试 import，使后续任务可复用新 support。
- 更新 `test-impact.json` 和测试基础设施回归测试，登记新 unit 目录并保留 legacy 过渡执行。

### 明确不做

不迁移写流程、查询流程、后台对账、HTTP、公共契约或真实数据库测试；不改变生产代码；不删除
legacy 目录或其验证命令。

### 实施步骤

1. 逐项确认纯规则测试保护的输入校验、身份与时间保持、敏感字段隐藏、媒体差异和状态汇总风险，
   删除只为覆盖率存在或断言私有实现的场景。
2. 把领域无关的 Backend 共享辅助代码留在 `backend/tests/support/`；只有 Cameras 专用内容进入
   `backend/tests/support/cameras/`，避免后续模块复制 Fake。
3. 将仍有价值的纯规则测试迁入 `backend/tests/unit/cameras/`，保持测试名称和失败消息使用简体中文。
4. 更新 legacy 测试 import，并用 `rg` 确认没有继续从已移走的 legacy helper 导入。
5. 调整 `backend-cameras` 的过渡命令：新 unit 目录与剩余
   `backend/tests/modules/cameras/` 必须同时执行；增加或更新选择器回归测试。
6. 从 legacy 删除已经迁移的 unit 测试文件和失去用途的 helper，未迁移测试继续保留。

### 验证方式

只运行 `./scripts/verify-changed.sh`。确认摘要包含 `backend-cameras`，并确认选择器测试证明新 unit 与
剩余 legacy 都会被执行；若脚本升级到 integration，则必须使用有效数据库环境。

### 完成标准

- Cameras 专用测试辅助代码全部位于 `backend/tests/support/cameras/`，legacy 测试能正常导入。
- 纯规则测试位于 `backend/tests/unit/cameras/`，不依赖数据库、HTTP 应用或 MediaMTX。
- 已迁移测试不再留在 legacy，统一验证入口通过。

### 与下一任务的衔接

02b 直接复用本任务稳定下来的 Builder 与 Fake 迁移创建、更新和默认预览源写流程；开始 02b 前不得
改回 legacy helper 路径。

## 导航

- [返回任务 2](./02-backend-cameras.md)
- [下一任务：02b 写流程 Module 测试](./02b-cameras-write-module.md)
