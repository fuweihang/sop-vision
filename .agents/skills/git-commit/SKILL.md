---
name: git-commit
description: 创建当前任务的 Git 提交。仅在用户明确要求提交时使用。
---

# Git Commit

1. 检查当前工作区、暂存区和相关差异，包括未跟踪文件；仅纳入当前任务修改。
2. 不得提交 `.env`、密钥、凭据、运行日志或其他本地数据；`.gitignore` 不能替代提交前检查。
3. 读取 `.github/instructions/commit-message.md`，基于实际暂存差异生成提交信息。
4. 创建提交前再次确认暂存内容和提交信息一致，然后执行提交。
5. 不得 amend、rebase、reset、force push 或改写已有历史，除非用户明确要求。
