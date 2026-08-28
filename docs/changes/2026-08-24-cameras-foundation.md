# 2026-08-24｜Cameras 基础能力

## 变化

- 建立 Camera/CameraSource 领域模型、PostgreSQL 持久化、Repository 和事务边界。
- 建立 Cameras HTTP 公共错误、严格 UUID、分页和敏感数据处理规则。
- 冻结 Camera MVP OpenAPI，并生成 Frontend 类型、Client、Query Key 与 MSW 场景。

## 影响

- 数据库新增 Cameras 相关迁移；部署必须使用 PostgreSQL 并执行 Alembic migration。
- Camera 路由进入 OpenAPI，但当时仍是占位 handler，不代表业务能力可用。
- API 和日志不得泄露密码、完整 RTSP URL、SQL 参数或数据库约束细节。

## 验证

使用 Backend 测试、Frontend 测试以及 `scripts/check-cameras-contracts.sh` 和
`scripts/check-cameras-sensitive-data.sh` 验证。

当前规则见 [Cameras 基础能力](../modules/cameras/foundation.md)。
