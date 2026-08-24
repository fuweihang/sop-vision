# 步骤 9｜契约门禁与 Foundation 收口

> 前置：[步骤 1–8](./README.md#4-执行顺序)  
> 产出：迁移、OpenAPI、生成类型、安全回归和实现说明的统一门禁

## 1. 完成目标

把 Foundation 的跨端约束变成可在 CI 重复执行的失败门禁，并给后续功能切片留下唯一更新流程。此步骤不增加产品行为。

## 2. 门禁流水线

按以下顺序执行，便于快速定位失败层：

1. Backend lint/format/unit tests。
2. PostgreSQL 空库 `upgrade head`、`downgrade base`、再次升级。
3. PostgreSQL Repository contract/integration tests。
4. 从 Backend 代码重新导出 OpenAPI。
5. 从 OpenAPI 重新生成 Frontend 类型。
6. 比较工作区产物，任何未提交漂移均失败。
7. Frontend lint/format/test/build。
8. 敏感数据与契约边界专项测试。

生成检查必须使用临时目录或生成后 diff，不允许依赖开发者记得手动提交生成文件。

## 3. 兼容性检查

至少识别并阻止以下未审阅变更：

- 字段删除、必填性改变、类型或 format 改变。
- 枚举值删除/重命名。
- operation ID 重复或改变。
- 已声明错误响应、Problem media type 或状态码消失。
- 列表/Playback Schema 新增敏感字段。
- 请求模型意外接受只读字段或未知字段。

MVP 阶段允许有意的破坏性变更，但必须同时更新事实源文档、后端 Schema、OpenAPI、前端生成类型和 Fixture，并在 PR 中显式说明；不能靠跳过门禁合并。

## 4. 安全回归

使用唯一测试秘密，例如 `foundation-leak-sentinel`，覆盖：

- Pydantic/领域校验错误。
- SQLAlchemy/Repository 异常。
- HTTP Problem body 与 headers。
- 应用、访问和测试捕获日志。
- OpenAPI examples、测试快照和 MSW 的非详情响应。
- Frontend console/error reporter/localStorage/sessionStorage/IndexedDB。

断言秘密和完整带凭据 RTSP URL均不存在。CameraDetail 的显式响应 Fixture 是唯一允许包含测试密码的边界，且仍不得持久化或进入日志。

## 5. 实现说明

更新 Backend/Frontend README 或 Foundation 实现说明，至少记录：

- 启动 PostgreSQL 与 Backend 的命令。
- Alembic upgrade/downgrade 和新增迁移流程。
- OpenAPI 导出、Frontend 类型生成及漂移检查命令。
- MSW 场景选择方式。
- Backend/Frontend 定向和完整测试命令。
- 当前 MVP 明文凭据语义、`no-store` 要求与禁止日志边界。
- Foundation 尚未实现任何 Camera 业务路由的事实。

## 6. 最终验收矩阵

| Foundation 事实 | 自动化证据 |
| --- | --- |
| 迁移可升级/回滚 | PostgreSQL migration job |
| UUID/无外键/唯一/显式关联清理生效 | DDL 与 Repository integration tests |
| 聚合规范化与连续排序 | pure domain tests |
| 原子保存与回滚 | Repository contract tests |
| 嵌套字段错误准确 | Backend + Frontend parser tests |
| OpenAPI/TS 同源 | regenerate-and-diff job |
| Mock 覆盖成功及 404/409/422/502/503 | MSW scenario tests |
| 密码/RTSP URL 不泄漏 | leak sentinel tests |
| 后续切片可替换依赖 | Fake UoW、固定 Clock/ID、MSW harness tests |

## 7. 退出条件

- 全部门禁在干净 checkout 上一次通过，不依赖人工准备数据库数据。
- 修改后端 Schema 而未重新生成 OpenAPI/TypeScript 时，CI 会稳定失败。
- Foundation 原始 README 的 7 项独立验收均有明确自动化证据。
- 后续切片可以只关注自己的 Application Service、route 和页面行为。
- 没有临时跳过、`xfail`、忽略未处理 MSW 请求或待补迁移测试。

## 8. 交付边界

本步骤完成即表示 Foundation 可以关闭。下一提交应从 `02-camera-create` 开始，不在 Foundation PR 中顺带实现创建 API 或表单。
