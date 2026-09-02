# 02｜Backend 默认预览源切换

## 任务目标

实现可用的 `PATCH /api/v1/cameras/{camera_id}/default-preview-source`
（`setDefaultPreviewSource`）。请求原子更新一个 Camera 的默认 Source ID 和聚合 `updated_at`，
成功返回最小确认响应，不修改 Source 配置、顺序或 MediaMTX Path。

## 当前上下文 / 前置条件

- [01｜Backend Camera 完整更新](../01-backend-camera-update/README.md)必须已经实施并通过验证。开始时
  以任务 01 落地后的 Application、错误映射、OpenAPI 和测试为准。
- 同时读取 [09 总计划](../README.md)、[Cameras 基础能力](../../../../modules/cameras/foundation.md)和
  [Camera 详情](../../../../modules/cameras/camera-detail.md)。
- `Camera.change_default_preview_source` 已实现 Source 所有权检查和更新时间推进；
  `CameraRepository.get(for_update=True)/save` 与 UoW 已能完整保存聚合。
- `SetDefaultPreviewSourceRequest`、`DefaultPreviewSourceResponse`、受控 OpenAPI、Frontend 生成
  类型和 Client 已预留；PATCH Router handler 当前仍是占位。

## 实施范围

- 新增框架无关的默认源 Application Service。使用请求级 UoW 锁定读取最新 Camera，找不到时返回
  `404 CAMERA_NOT_FOUND`。
- 调用现有领域行为确认目标 Source 属于该 Camera。Source 不存在或属于其他 Camera 时返回
  `422 VALIDATION_ERROR` 和 `source_id/SOURCE_NOT_OWNED_BY_CAMERA`。
- 离线 Source 与没有 `whep_url` 的 Source 仍可设为默认；Application 不读取 Runtime State，也不
  探测摄像头。
- 重复选择当前默认 Source 仍按一次明确写请求推进 `updated_at`，然后完整保存并提交聚合。
- 已知保存或提交失败回滚未提交修改；数据库提交结果无法确认时返回现有
  `503 DATABASE_UNAVAILABLE`。
- 持久化数据无法重建合法聚合时，结束事务并返回 `500 CAMERA_AGGREGATE_INVALID`，不携带领域
  issues。
- 成功响应只包含 `camera_id/default_preview_source_id/updated_at`；PATCH 不返回 CameraDetail，
  不需要 no-store Header。
- 替换占位 Router，接通 UoW 和 Clock；同步 PATCH 的 `500` OpenAPI 声明、生成类型、Fixture、
  MSW 和契约测试。
- 全用例不得调用 `ensure_path`、`release_path`、Runtime Path 快照或其他 Stream Gateway 方法。

## 明确不做

- 不实现 Frontend 默认源单选、查询失效或播放器切换。
- 不修改 Source 名称、后缀、顺序、默认源以外的 Camera 字段或 MediaMTX 配置。
- 不根据 Source 在线状态拒绝请求，不为相同默认源做 no-op 优化。
- 不引入局部 Source Repository、通用 Patch Service、版本控制或幂等协议。
- 不修改任务 01 已完成的 PUT 行为，不执行 11 的真实依赖验收。
- 本任务完成后不更新长期能力文档或移除 09；统一由任务 05 处理。

## 实施步骤

1. 以任务 01 的写事务和错误转换为样式，新增默认源 Command/Result 与 Application Service。
2. 实现锁定读取、领域变更、完整保存、提交/回滚和最小结果映射。
3. 为不存在、跨 Camera Source、离线 Source、重复选择、损坏聚合、数据库失败和取消增加测试。
4. 用 Fake 明确断言全部分支零 Stream Gateway 调用。
5. 替换 PATCH 占位 handler，更新依赖、响应 Mapper、OpenAPI、生成类型、Fixture 与 API 测试。
6. 使用独立 PostgreSQL 验证默认 ID 和时间原子保存，以及同 Camera PUT/PATCH 写入按锁串行。

## 验证方式

```bash
# 仓库根目录
bash scripts/check-cameras-contracts.sh
bash scripts/check-cameras-sensitive-data.sh

# backend/
uv run --env-file .env.local pytest tests/modules/cameras
uv run ruff check .
uv run ruff format --check .

# frontend/
pnpm exec vitest run \
  src/features/cameras/api/cameras-api.test.ts \
  src/mocks/cameras/fixtures.test.ts \
  src/mocks/cameras/scenarios.test.ts
pnpm lint
pnpm format:check
pnpm build
```

PostgreSQL 测试必须配置独立 `TEST_DATABASE_URL`，跳过时不能算作完整验收。

## 完成标准

- PATCH handler 不再是占位，成功返回最小确认响应并推进聚合更新时间。
- 所属 Source、离线 Source、重复选择、Camera 不存在、聚合损坏和数据库失败均按契约通过测试。
- 数据库只保存默认 ID 和 Camera 更新时间变化，Source 配置与顺序保持不变。
- Application、API 和集成测试证明所有分支零媒体调用。
- OpenAPI、生成类型、Client、Fixture、MSW 和敏感数据检查无漂移。

## 与下一任务的衔接

下一步执行 [03｜Frontend Camera 编辑 Dialog](../03-frontend-camera-edit/README.md)。开始时两个 Backend
写端点都应已经可用，Frontend 可以直接使用最终生成类型和现有 `updateCamera` Client；不得再使用
MSW 占位行为代替真实 Backend 契约。
