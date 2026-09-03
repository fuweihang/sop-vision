# 2026-09-03｜测试目录与按变更验证

## 变化

- Backend 测试统一放在 `backend/tests/<layer>/<module>/`，Frontend 测试统一放在
  `frontend/tests/<layer>/<module>/`，测试工具放在 `tests/unit/test_infrastructure/`。
- 公共 Fixture、Builder、Fake 和 Setup 放在对应测试根的 Support 目录，并在 `test-impact.json` 中登记
  实际使用模块。
- 日常交付统一运行 `./scripts/verify-changed.sh`。脚本按变更路径、受影响模块和变更规模选择 unit、
  module 或 integration 检查，并把完整输出保存到临时日志。
- 测试目录检查会扫描仓库中全部已跟踪及未忽略的现存测试，拒绝未登记、重复归属或源码旁测试；
  实际业务测试仍只按当前 Git 变更选择。

## 影响

- 新增或移动测试时，必须先选择一个明确的平台、层级和模块；新增 Support 时还要登记使用模块和最低
  验证级别。
- 未在 `test-impact.json` 中登记、也未明确忽略的生产文件变化会停止交付检查，避免新模块静默跳过
  测试。
- Pytest、Vitest、API Contract、真实 PostgreSQL、MediaMTX 和浏览器命令保留用于失败排查或额外环境
  验收，不再作为每次日常交付都手工执行的命令清单。
- API、数据库结构、配置、部署方式和运行时业务行为均无变化。

## 验证

使用统一入口验证测试目录、影响选择、模块传播、规模升级以及对应的 Backend/Frontend 测试命令；
同时盘点现存生产、协议、测试与 Support 路径，确认均有明确登记或合理例外。

## 相关长期文档

- [仓库测试与交付规则](../../AGENTS.md)
- [Cameras 公共验证入口](../modules/cameras/README.md#公共验证入口)
- [Backend 日志验证与排障](../modules/backend-logging/README.md#验证)
