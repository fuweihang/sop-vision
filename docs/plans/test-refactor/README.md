# 测试代码重构计划

## 目标与执行方式

把现有 Backend 和 Frontend 测试重构到项目规定的“层级 + 模块”目录，并按 `test-policy`
重新判断每个测试的价值和最低有效层级。完成后保持以下职责分工：

```text
编写阶段：AI 判断是否需要测试、测试内容、层级和模块
交付阶段：AI 只调用 ./scripts/verify-changed.sh
选择阶段：脚本根据 test-impact.json 决定实际测试范围
```

每个任务使用一个独立 Codex 会话，必须按下面的顺序执行，不要并行。Backend 先整理 Core 和共享
测试辅助代码，再迁移 Cameras 与 Stream Gateway。Core 的生产实现不依赖下游测试先迁移，但
`test-impact.json` 必须在过渡期间继续用旧目录运行尚未迁移的下游测试；每个下游任务完成时再把
对应命令切换到新目录，避免统一验证入口命中不存在的路径。

## 通用执行要求

每个会话开始前，重新读取当前版本的 `AGENTS.md`、`.agents/skills/test-policy/SKILL.md`、
`test-impact.json`，并读取任务涉及平台的 Backend 或 Frontend 参考。判断测试是否低价值或易碎时，
读取 `.agents/skills/test-policy/references/test-smells.md`。

1. 不按旧文件位置机械搬运。先明确测试要防止的缺陷，再决定保留、合并、重写或删除。
2. 选择能够稳定捕获风险的最低层级，不为了覆盖率或目录完整机械增加测试。
3. 公共 Fixture、Builder、Fake 和 Setup 放到对应测试根目录的 `support/`。
4. 默认不修改生产代码行为；发现生产问题时记录问题，不扩大当前任务范围。
5. 不新增 E2E 或视觉测试体系。只有迁移结果证明影响规则不正确时，才最小修改
   `test-impact.json` 或脚本，并增加测试工具回归测试。
6. 完成后只运行 `./scripts/verify-changed.sh`。失败时先用 `rg` 检索脚本给出的临时日志，再按需
   读取局部内容，不把完整日志送入 AI 上下文。
7. 删除当前任务中已经迁移的旧测试和失去用途的辅助代码，不长期保留两套测试。

## 任务执行顺序

1. [Backend Core 测试重构](./01-backend-core.md)
2. [Backend Cameras 测试重构](./02-backend-cameras.md)
3. [Backend Stream Gateway 测试重构](./03-backend-stream-gateway.md)
4. [Frontend Cameras 测试重构（04a～04h）](./04-frontend-cameras.md)
5. [Frontend Video 测试重构（05a～05d）](./05-frontend-video.md)
6. [Frontend Shared 与 App Shell 测试重构](./06-frontend-shared-app-shell.md)
7. [跨端契约与迁移验收](./07-cross-platform-contract-and-acceptance.md)

## 完成计划

第七个任务通过后，按上级 [plans 完成规则](../README.md) 补充必要的模块文档和变更记录，再移除
本计划。
