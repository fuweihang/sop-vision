---
name: test-policy
description: 根据 SOP Vision 的测试层级、模块归属和变更风险设计或修改测试。适用于生产代码行为变化、Bug 修复以及测试代码审查；不用于纯文档、Git 或 PR 操作。
---

# 测试策略

测试可观测行为和明确风险，不断言私有状态、内部调用次数或框架胶水。优先扩展已有测试；只有在职责独立时才创建新文件。Bug 可以稳定复现时必须添加回归测试。

## 确定测试位置

每个测试必须有一个主模块和一个测试层级，并放入对应目录：

- Backend：`backend/tests/<layer>/<module>/...`
- Frontend：`frontend/tests/<layer>/<module>/...`
- 测试工具：`tests/unit/test_infrastructure/...`

公共 Fixture、Builder、Fake 和 Setup 放在各测试根目录的 `support/` 中，不伪装成业务测试。模块名和允许的路径以 `test-impact.json` 为准，不自行创建新的模块别名。

## 选择最低有效层级

先明确要防止的缺陷，再选择足以稳定复现它的最低层级：

- 隔离的纯规则、状态转换和确定性计算使用 unit。
- 一个业务模块内部多个对象协作，Backend 使用 module；Frontend UI 行为使用 component。
- 公共 HTTP、生成类型或外部协议兼容性使用 contract。
- 真实数据库、文件系统、外部适配器或跨模块运行流程使用 integration。
- E2E 和 visual 只用于低层级测试无法可靠覆盖的关键流程，不纳入日常变更测试的默认升级链。

不要为了覆盖率机械补齐正常、边界、失败和回归四类场景，只选择与本次风险有关的情况。默认不添加快照、穷举组合、休眠等待或大范围 Mock。

需要具体判断时，只读取对应参考：

- Backend：`references/backend.md`
- Frontend：`references/frontend.md`
- 判断测试是否低价值或易碎：`references/test-smells.md`

## 验证

完成代码和测试修改后只运行：

`./scripts/verify-changed.sh`

脚本会根据文件路径、受影响模块和变更规模，在 unit、module、integration 之间升级，并把完整输出写入临时日志。成功时只保留摘要；失败时先根据终端给出的日志路径使用 `rg` 定位关键错误，再按需读取局部内容。

除非定位该脚本报告的失败，不要手工缩小测试范围，也不要默认运行全量测试。数据库 integration 被选中但本地缺少 `backend/.env.local` 或 `TEST_DATABASE_URL` 时，应报告环境缺失，不得把跳过测试当成通过。
