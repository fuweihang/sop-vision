---
name: pull-request
description: 创建、准备或更新当前分支的 Pull Request。仅在用户明确要求对应 PR 操作时使用。
---

# Pull Request

1. 确认当前分支、远端默认目标分支、已有 PR、未推送提交和未提交修改；主分支不能直接作为 PR 来源分支。
2. 检查目标分支到当前分支的全部提交和最终差异，不用单个 commit message 代替实现分析。
3. 存在相关 Issue、模块文档或设计文档时读取它们，用于确认目标和建立关联。
4. 读取 `.github/instructions/pull-request.md`，根据实际差异准备标题与描述。
5. 创建新 PR 前确认当前分支没有已有 PR；更新 PR 时只修改用户指定或当前分支对应的 PR。
6. 未经用户明确要求，不修改、合并或关闭其他 PR / Issue，也不改写已有历史。
