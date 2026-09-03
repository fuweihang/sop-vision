# 测试基础设施

测试基础设施负责测试目录约束、变更影响登记、日常验证范围选择和日志输出。业务测试仍由各业务
模块维护；本模块只决定测试放在哪里、一次变更需要运行哪些检查，以及遗漏登记时如何阻止交付。

## 目录与归属

每个测试必须同时有一个平台、一个测试层级和一个主模块：

```text
backend/tests/<layer>/<module>/...   # Backend 业务测试
frontend/tests/<layer>/<module>/...  # Frontend 业务测试
tests/unit/test_infrastructure/...   # 仓库级测试工具回归测试
```

Backend 当前使用 `unit`、`module`、`contract`、`integration`；Frontend 当前使用 `unit`、
`component`、`contract`、`integration`。`e2e` 与 `visual` 尚无日常测试入口，不能直接混入现有
目录。

公共 Fixture、Builder、Fake 和 Setup 放在对应测试根的 `support/` 中。Support 不是独立业务模块；
除只建立 Python 包边界的 `__init__.py` 外，每个 Support 路径仍须在 `test-impact.json` 的 `source`
规则中登记实际使用模块和最低验证级别。

`scripts/test_policy_check.py` 扫描全部已跟踪及未忽略的现存文件，并拒绝以下情况：

- Backend 或 Frontend 源码目录中重新出现测试；
- 测试不属于任何已登记模块，或同时属于多个模块；
- Support 文件没有登记受影响模块。

模块名、允许路径和命令以仓库根的 [`test-impact.json`](../../../test-impact.json) 为准。设计或修改
测试时遵循 [`test-policy`](../../../.agents/skills/test-policy/SKILL.md)，不要根据旧目录自行创建
模块别名。

## 按变更选择验证

日常交付统一从仓库根目录运行：

```bash
./scripts/verify-changed.sh
```

入口先检查全仓测试目录，再收集相对 `origin/main` 的分支提交、暂存区、工作区和未忽略的未跟踪
文件。`scripts/test_changed.py` 用 `test-impact.json` 完成以下选择：

1. 每个命中路径按登记规则请求 `unit`、`module` 或 `integration` 验证级别。
2. 上游模块变化会把登记的下游影响模块加入本次验证，跨模块影响至少使用 `module` 级别。
3. 变更文件数或受影响模块数达到配置阈值时继续升级；精确阈值只在 `test-impact.json` 维护。
4. 未登记且未明确忽略的现存生产路径会直接失败，防止新增模块静默跳过测试。
5. 只有文档或已忽略入口变化时仍执行目录检查，但不运行业务测试。

这里的 `unit`、`module`、`integration` 是一次交付的验证强度，不等同于所有测试目录名称。例如
Frontend 的 `component` 与 `contract` 测试由所属模块在 `module` 级命令中运行。

选择出的命令顺序执行。完整 stdout/stderr 写入系统临时目录
`sop-vision-verify-*`；终端成功时只显示模块和耗时，失败时显示少量关键行及完整日志路径。不要提交
这些临时日志。

## 数据库与外部依赖

Backend integration 被选中时，验证入口优先读取 `backend/.env.local`；没有该文件时使用进程中的
`TEST_DATABASE_URL`。两者都不存在会以环境缺失失败，不把 PostgreSQL 测试跳过当作通过。

真实 MediaMTX、跨端 OpenAPI、敏感数据和 vendored reader 检查由对应模块的 integration 或
API Contract 命令调用。项目 CI 仍执行完整 Backend/Frontend 测试、静态检查、构建和专项门禁；
按变更验证是本地日常交付入口，不替代发布计划中的真实浏览器、设备和容量验收。

## 修改与排障

- 新增生产模块、测试层级、Support 或质量命令时，先更新 `test-impact.json`，并在
  `tests/unit/test_infrastructure/` 增加选择或目录门禁回归测试。
- 统一入口失败时，先用终端给出的日志路径和 `rg` 定位错误；只在需要复现时运行日志中的 Pytest、
  Vitest 或专项命令。
- `scripts/test-changed.sh` 和 `scripts/test-policy-check.sh` 是两个阶段的独立排障入口，不作为常规
  交付命令。
- `pnpm test`、完整 `pytest`、覆盖率和发布专项门禁保留用于 CI、排障或额外验收，不应取代
  `./scripts/verify-changed.sh`。

当前限制是没有 E2E 与视觉回归的环境、基准和影响规则。确需新增时，必须同时定义运行环境、失败
产物、模块归属和选择规则。
