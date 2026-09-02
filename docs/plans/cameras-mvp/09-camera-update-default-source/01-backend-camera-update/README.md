# 01｜Backend Camera 完整更新

## 任务目标

实现可用的 `PUT /api/v1/cameras/{camera_id}`（`updateCamera`）。一次请求完整替换 Camera 可变配置
和 Source 集合，在同一数据库事务中完成增删改排与默认源变化；提交后只同步实际变化的 MediaMTX
Path，并返回 `200 CameraDetail` 和 `Cache-Control: no-store`。

## 当前上下文 / 前置条件

- 开始前读取 [09 总计划](../README.md)、[Cameras 基础能力](../../../../modules/cameras/foundation.md)、
  [Camera 创建](../../../../modules/cameras/camera-create.md)、
  [Camera 详情](../../../../modules/cameras/camera-detail.md)和
  [媒体对账](../../../../modules/cameras/media-reconciliation.md)。
- `Camera.update_configuration` 已实现完整集合更新、Source ID 所有权检查、默认源约束、后缀规范化、
  新 ID 和时间生成；不得在 Application 或 API 层复制这些规则。
- Camera Repository 已提供 `get(for_update=True)` 和聚合级 `save`，UoW 已提供显式
  `commit/rollback`；PostgreSQL 实现会按 Camera → Source 的固定顺序加锁。
- 创建和详情已经提供安全 Desired State 构造、Runtime Path 快照投影、Camera 状态汇总和
  `CameraDetail` Mapper，应直接复用。
- PUT 请求/响应 Schema、受控 OpenAPI、Frontend 生成类型和 Client 已预留；Router handler 当前仍
  只抛出 `NotImplementedError`。

开始实施时必须再次核对当前代码、迁移、OpenAPI 和测试，不能用本计划替代已经变化的实现事实。

## 实施范围

### 请求与事务

- PUT 保持完整替换语义：已有项用稳定 `source_id` 识别，无 ID 项新增，请求中缺失的旧项删除，
  数组顺序成为连续 `sort_order`，唯一 `is_default_preview=true` 项成为默认源。
- Application Command 必须关闭包含密码和 Source 后缀的默认 `repr`。服务从请求级 UoW
  `get(camera_id, for_update=True)` 读取最新聚合，再调用现有领域行为生成新聚合。
- 保留项继续使用原 `source_id/created_at`；新增项使用注入的 `IdGenerator`；全部更新时间使用注入
  的 `Clock`。
- Repository `save` 与 `commit` 必须在一个事务内完成。已知失败显式回滚未提交修改；提交结果
  无法确认时仍转换为现有 `503 DATABASE_UNAVAILABLE`，不声称数据库一定没有提交。
- 服务端不增加版本字段、ETag 或前端版本比较。相同 Camera 的写请求继续按现有行锁串行执行，后取得
  锁并提交的合法请求成为最新数据库状态。

### 校验与错误

| 场景                 | 公开结果                                          |
| -------------------- | ------------------------------------------------- |
| Camera 不存在        | `404 CAMERA_NOT_FOUND`                            |
| 非标准 Source UUID   | `sources[i].source_id/INVALID_UUID`               |
| Source 不属于 Camera | `sources[i].source_id/SOURCE_NOT_OWNED_BY_CAMERA` |
| 请求内重复 Source ID | 后续项 / `DUPLICATE_SOURCE_ID`                    |
| 规范化后缀重复       | 后续项 / `DUPLICATE_SOURCE_SUFFIX`                |
| 无 Source            | `sources/SOURCE_REQUIRED`                         |
| 无或多个默认源       | 沿用 Camera 创建的默认源字段错误                  |
| 只读或未知字段       | 对应字段 / `UNKNOWN_FIELD`                        |
| 持久化聚合损坏       | `500 CAMERA_AGGREGATE_INVALID`                    |
| 数据库操作不可用     | `503 DATABASE_UNAVAILABLE`                        |

- 空 Source 数组在 HTTP Schema 和直接调用 Domain/Application 时都必须稳定得到
  `SOURCE_REQUIRED`，不能因 Pydantic `minItems` 退化为通用范围错误。
- Repository 重建聚合失败时，Application 必须结束事务并转换为不携带领域 issues 的
  `CameraAggregateInvalidError`；该分支不得访问 Stream Gateway。
- `CameraPersistenceOperationError` 沿用 `503 DATABASE_UNAVAILABLE`。无法准确定位到本次请求字段的
  `CameraConstraintViolationError` 或服务端不变量错误沿用安全 `500 INTERNAL_SERVER_ERROR`；只有
  Application 能确定请求数组下标时才返回字段级 `422`，不得把所有数据库约束冲突统一改写为
  `503` 或猜测成用户输入错误。
- 更新 Router 的公共 `500` 声明，并同步 Backend Schema、受控 OpenAPI、Frontend 生成类型、Client
  类型断言、MSW 与 Fixture。不得公开 Pydantic 原始 input、SQL、参数、约束名或底层异常文本。

### 提交后媒体 diff

- 在数据库提交前保存旧聚合；提交后比较旧、新聚合生成的 Desired State，不重新查询数据库来猜测
  本次 diff。
- Source 只改名称或排序时不调用 `ensure_path`，也不重载现有媒体连接。
- 新增 Source、后缀变化的保留 Source 调用 `ensure_path`。Camera IP、端口、用户名或密码变化时，
  为全部新聚合 Source 调用 `ensure_path`。
- 已删除 Source 调用 `release_path`。先按新聚合 Source 顺序完成所有 ensure，再按旧聚合顺序释放
  删除项；单项受支持故障不阻止其余操作。
- 只捕获 Stream Gateway Port 声明的不可用或无效响应；任务取消和程序缺陷继续传播。媒体故障不能
  回滚或反向修改已提交数据库配置，后台对账负责恢复。
- 数据库锁在 `commit` 后释放，不跨提交持有行锁等待 MediaMTX。相同 Camera 的并发请求可能让提交后
  的媒体调用交错并短暂写入旧 Desired State；本任务接受该短暂窗口，由后台对账按最新数据库配置
  恢复，不增加版本、Outbox、分布式锁或跨实例协调。真实多实例交错验收仍属于任务 11。
- 即时同步完成后只读取一次 Runtime Path 快照，复用详情的投影和 Camera 状态汇总返回
  `CameraDetail`。受支持的快照故障使用同一次失败完成时间投影，仍返回 `200`。
- 日志不得记录 Command、Camera/Source 集合、凭据、后缀、Desired State、完整 RTSP URL、远端响应
  或原始异常文本。

## 明确不做

- 不实现默认源 PATCH、Frontend 编辑 Dialog、默认源单选或播放器联动。
- 不修改 Camera 删除、对账调度、Stream Gateway 公共协议或 Session Manager。
- 不增加通用 CRUD Service、Generic Repository、Outbox/Saga、幂等键或写冲突 UI。
- 不连接真实 MediaMTX，不执行进程崩溃、多实例、真实设备、网络和容量门禁；这些属于
  [11｜发布门禁](../../11-release-gates/README.md)。
- 本任务完成后不提前更新长期能力文档，也不移除 09；统一由任务 05 收尾。

## 实施步骤

1. 以现有创建、详情服务为样式新增脱敏的 Update Command/Result 和框架无关 Application Service。
2. 新增纯媒体 diff，覆盖无变化、新增、删除、后缀变化、连接字段变化和组合变化。
3. 实现锁定读取、领域更新、聚合保存、提交/回滚、提交后媒体操作及单次运行态投影。
4. 扩展测试 Fake，使 ensure、release、快照、数据库读取/保存/提交/回滚和调用顺序都可独立断言。
5. 替换 PUT 占位 handler，注入 UoW、Stream Gateway、IdGenerator 和 Clock，设置 no-store 响应。
6. 补齐损坏聚合和数据库错误转换，更新 OpenAPI 响应声明、生成类型、Fixture 与契约测试。
7. 增加领域边界、Application、API、Repository/PostgreSQL 并发、媒体失败和敏感数据回归测试。
   明确覆盖提交前取消会回滚且零媒体调用，以及提交后媒体阶段取消继续传播且不反向修改数据库。

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

PostgreSQL 保存、回滚和并发测试必须配置独立 `TEST_DATABASE_URL`；相关测试被跳过时，本任务不能算
完整通过。媒体行为只使用可控 Fake，确保失败测试确定且不依赖外部服务。

## 完成标准

- PUT handler 不再是占位，正确返回完整 `CameraDetail` 和 `Cache-Control: no-store`。
- 增删改排、默认源、稳定 ID/时间、所有权和字段错误均按公开路径验证。
- 已知数据库失败不留下部分修改；同 Camera 并发更新按锁串行，最终数据库状态对应最后完成的合法
  更新。
- 提交前取消会回滚且不访问媒体；提交后媒体阶段取消会原样传播，已经提交的数据库配置保持不变。
- 精确媒体 diff、ensure-before-release、单项失败继续、单次快照和媒体降级 `200` 均通过测试。
- 损坏聚合返回安全 `500` 且零媒体调用；契约、生成类型、Fixture 和敏感数据检查无漂移。

## 与下一任务的衔接

下一步执行 [02｜Backend 默认预览源切换](../02-backend-default-preview-source/README.md)。下一任务应
复用本任务已经落地的请求级写事务、损坏聚合转换和契约同步方式，但不能把两个用例合并成通用写
Service，也不能为默认源 PATCH 调用媒体接口。
